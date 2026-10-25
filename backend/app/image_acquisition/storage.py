"""
Where the Sentinel-2 GeoTIFFs live on disk.

Each year can live on a different drive (e.g. 2016-2019 on one disk,
2020-2025 on another). There is no separate settings file: the DB is the
single source of truth. ``lake_images.file_path`` and
``lake_tiles.image_path`` record where every lake-year was written, with the
layout::

    <root>/<year>/lake_<id>/tile_<i>.tif     tiles
    <root>/<year>/lake_<id>.tif              merged image

so the folders a year's files are in are read back from those paths
(:func:`summarise_year_roots`). A download writes new files to the root
chosen for the run, else to ``SENTINEL_DATA_DIR`` (default
``backend/data/sentinel``, i.e. ``backend/data/sentinel/<year>/``).
Merge writes next to the tiles; features and embeddings follow
``lake_images.file_path``.

Paths in the DB are relative to the backend folder when the file is inside
it, and absolute otherwise. They are always resolved against the backend
folder, so they stay valid whatever root is used later.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Filesystems worth offering as a download location (skips tmpfs, squashfs, …)
_DATA_FS_TYPES = {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "ntfs", "ntfs3", "fuseblk", "exfat", "vfat"}
_SKIP_MOUNT_PREFIXES = ("/boot", "/snap", "/proc", "/sys", "/dev", "/run/user", "/var/lib")


def default_data_root() -> Path:
    """The root from ``SENTINEL_DATA_DIR`` (relative to the backend folder)."""
    root = Path(settings.SENTINEL_DATA_DIR).expanduser()
    return root if root.is_absolute() else BACKEND_ROOT / root


def root_of_stored_path(stored_path: str, year: int) -> Optional[Path]:
    """Storage root of a ``lake_images`` / ``lake_tiles`` path, or ``None``
    if the path does not follow the ``<root>/<year>/lake_<id>…`` layout
    (e.g. a Google Drive export path)."""
    if not stored_path:
        return None
    path = resolve_stored_path(stored_path)
    for parent in (path.parent, path.parent.parent):
        if parent.name == str(year) and parent.parent != parent:
            return parent.parent
    return None


def summarise_year_roots(rows: Iterable) -> Dict[int, List[Dict]]:
    """Group ``(year, stored_path, updated_at)`` rows by year and root.

    Returns ``{year: [{"root", "lakes", "last_used"}, …]}`` with the most
    recently used root first — that is the root the year "currently" uses.
    """
    acc: Dict[int, Dict[Path, Dict]] = {}
    for year, stored_path, updated_at in rows:
        root = root_of_stored_path(stored_path, year)
        if root is None:
            continue
        entry = acc.setdefault(year, {}).setdefault(
            root, {"root": root, "lakes": 0, "last_used": updated_at}
        )
        entry["lakes"] += 1
        if updated_at and (entry["last_used"] is None or updated_at > entry["last_used"]):
            entry["last_used"] = updated_at
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return {
        year: sorted(roots.values(), key=lambda e: e["last_used"] or epoch, reverse=True)
        for year, roots in acc.items()
    }


def _normalise(raw: str) -> Path:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Storage location is empty.")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValueError("Storage location must be an absolute path (e.g. /media/data/sentinel).")
    path = Path(os.path.normpath(path))
    if path.exists() and not path.is_dir():
        raise ValueError(f"{path} exists and is not a directory.")
    return path


def check_data_root(raw: str) -> Path:
    """Like :func:`validate_data_root` but without creating anything.

    The directory, or the nearest parent that exists, must be writable.
    """
    path = _normalise(raw)
    probe = path
    while not probe.exists():
        probe = probe.parent
    if not probe.is_dir() or not os.access(probe, os.W_OK | os.X_OK):
        raise ValueError(f"{probe} is not writable.")
    return path


def validate_data_root(raw: str) -> Path:
    """Return the absolute, writable directory for ``raw`` or raise ValueError.

    The directory is created if it does not exist yet.
    """
    path = _normalise(raw)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Cannot create {path}: {exc.strerror or exc}") from exc

    probe = path / ".ecotwin_write_test"
    try:
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as exc:
        raise ValueError(f"{path} is not writable: {exc.strerror or exc}") from exc
    return path


def to_stored_path(path: Path) -> str:
    """DB form of ``path``: relative to the backend folder if inside it."""
    try:
        return str(path.relative_to(BACKEND_ROOT))
    except ValueError:
        return str(path)


def resolve_stored_path(stored_path: str) -> Path:
    """Absolute path for a ``file_path`` / ``image_path`` read from the DB."""
    path = Path(stored_path)
    return path if path.is_absolute() else BACKEND_ROOT / path


def disk_usage(path: Path) -> Optional[Dict[str, int]]:
    """Free / total bytes of the filesystem holding ``path`` (or its nearest
    existing parent). ``None`` if nothing on the way up exists."""
    probe = path
    while not probe.exists():
        if probe.parent == probe:
            return None
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    return {"free_bytes": usage.free, "total_bytes": usage.total}


def suggest_locations() -> List[Dict]:
    """Mounted data drives (Linux) the user can pick as a storage root."""
    suggestions: List[Dict] = []
    seen = set()

    def add(path: Path, label: str) -> None:
        key = str(path)
        if key in seen:
            return
        usage = disk_usage(path)
        if usage is None:
            return
        seen.add(key)
        suggestions.append({"path": key, "label": label, **usage})

    add(default_data_root(), "Default (SENTINEL_DATA_DIR)")

    try:
        with open("/proc/mounts") as fh:
            mounts = [line.split()[:3] for line in fh]
    except OSError:
        mounts = []

    for _device, mount_point, fs_type in mounts:
        mount_point = mount_point.replace("\\040", " ")
        if fs_type not in _DATA_FS_TYPES or mount_point == "/":
            continue
        if mount_point.startswith(_SKIP_MOUNT_PREFIXES):
            continue
        if not os.access(mount_point, os.W_OK):
            continue
        add(Path(mount_point) / "ecotwin_sentinel", f"Drive {Path(mount_point).name or mount_point}")

    return suggestions
