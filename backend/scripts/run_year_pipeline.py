"""
Run the per-year pipeline through the backend API, one year after another.

  download thread:   fetch images for each year in turn (one download at a time),
                     through the backend API
  processing thread: as soon as a year's download is done →
                     merge tiles (delete tiles) → generate embeddings → generate features,
                     each in its own short-lived Python process

Processing runs outside the API server on purpose: Prithvi, merging and
feature extraction build up several GB in a long-lived process, which got the
server OOM-killed on an 8 GB machine. A fresh process per step frees all of
it. (The pop-ups therefore do not show these steps' progress; this log does.)

So the next year downloads while the previous one is processed. Every step
skips work that is already done, so the script can be stopped and started
again (e.g. with --years starting from the year that was interrupted).

Usage (from backend/, with the API running on localhost:8000; processing
steps use this backend's settings, so pass the same DB environment the
server uses, e.g. DATABASE_URL_OVERRIDE= POSTGRES_HOST=localhost):
    python scripts/run_year_pipeline.py \\
        --years 2019 2020 2021 2022 2023 2024 2025 2016 2017 \\
        --root /media/vikash/Entertainment/ecotwin_sentinel

A download already running for the first year is waited for, not restarted.
Only the standard library is used.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PYTHON = BACKEND_DIR.parent / ".venv" / "bin" / "python"

API = "http://localhost:8000/api/v1"
POLL_SEC = 30
_print_lock = threading.Lock()
summary: dict = {}


def log(msg: str) -> None:
    with _print_lock:
        print(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}", flush=True)


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except Exception:
            return exc.code, {"detail": str(exc)}


def get(path: str) -> dict:
    """GET with retries (the API may be briefly unreachable)."""
    while True:
        try:
            return call("GET", path)[1]
        except Exception as exc:
            log(f"  ! GET {path} failed ({exc}); retrying")
            time.sleep(POLL_SEC)


def start(path: str, body: dict, label: str) -> None:
    """POST a start request; wait while another run blocks it (HTTP 409)."""
    while True:
        try:
            code, resp = call("POST", path, body)
        except Exception as exc:
            log(f"  ! {label}: request failed ({exc}); retrying")
            time.sleep(POLL_SEC)
            continue
        if code == 200:
            return
        if code == 409:
            log(f"  {label}: busy ({resp.get('detail')}); waiting")
            time.sleep(60)
            continue
        raise RuntimeError(f"{label}: HTTP {code} {resp}")


def wait_until_done(status_path: str, active=("running", "cancelling")) -> dict:
    while True:
        p = get(status_path)
        if p.get("status") not in active:
            return p
        time.sleep(POLL_SEC)


def counts(p: dict, keys) -> str:
    return ", ".join(f"{k} {p.get(k)}" for k in keys if k in p)


# ── Steps ─────────────────────────────────────────────────────────────────


def download(year: int, root: str, first: bool) -> dict:
    status = get("/imagery/status")
    running_year = list((status.get("year_roots") or {}).keys())
    if first and status.get("status") in ("running", "cancelling") and running_year == [str(year)]:
        log(f"[{year}] download already running — waiting for it")
    else:
        body = {"years": [year], "lake_ids": None, "confirmed": True, "year_roots": {str(year): root}}
        start("/imagery/fetch", body, f"[{year}] download")
        log(f"[{year}] download started → {root}/{year}/")
    p = wait_until_done("/imagery/status")

    # One retry pass for failed tiles (completed tiles are skipped)
    if p.get("failed"):
        log(f"[{year}] download finished with {p['failed']} failed lake-years — retrying them once")
        body = {"years": [year], "lake_ids": None, "confirmed": True, "year_roots": {str(year): root}}
        start("/imagery/fetch", body, f"[{year}] download retry")
        retry = wait_until_done("/imagery/status")
        p = {**p, "failed": retry.get("failed"), "errors": retry.get("errors", [])}
    keys = ("status", "processed", "success", "skipped", "failed", "tiles_completed", "tiles_failed")
    log(f"[{year}] DOWNLOAD done: {counts(p, keys)}")
    for e in (p.get("errors") or [])[-10:]:
        log(f"[{year}]   error: {e[:200]}")
    return p


# Each processing step: run the pipeline function in a fresh process and print
# a JSON summary (result counts + the progress errors) as the last line.
_STEP_CODE = {
    "merge": (
        "from app.image_acquisition.merge_pipeline import run_merge_pipeline as f, get_merge_progress as g\n"
        "r = f(years=[{y}], delete_tiles=True)"
    ),
    "embeddings": (
        "from app.embedding_pipeline.pipeline import run_embedding_pipeline as f, get_embedding_progress as g\n"
        "r = f(years=[{y}])"
    ),
    "features": (
        "from app.services.lake_feature_generator import generate_lake_features as f, get_feature_progress as g\n"
        "r = f(year={y})"
    ),
}


def run_step(name: str, year: int) -> dict:
    code = (
        "import json, logging\n"
        + _STEP_CODE[name].format(y=year)
        + "\np = g()\n"
        + "print('__RESULT__' + json.dumps({**r, 'status': p.get('status'), 'errors': p.get('errors', [])[-20:]}))\n"
    )
    log(f"[{year}] {name} started (separate process)")
    proc = subprocess.run(
        [str(PYTHON), "-c", code],
        cwd=BACKEND_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    result = None
    for line in proc.stdout.splitlines():
        if line.startswith("__RESULT__"):
            result = json.loads(line[len("__RESULT__"):])
    if result is None:
        tail = (proc.stderr or proc.stdout)[-800:]
        raise RuntimeError(f"exit code {proc.returncode}: {tail}")
    keys = {
        "merge": ("status", "success", "skipped", "failed"),
        "embeddings": ("status", "success", "skipped", "failed"),
        "features": ("status", "total", "processed", "skipped", "failed"),
    }[name]
    log(f"[{year}] {name.upper()} done: {counts(result, keys)}")
    for e in (result.get("errors") or [])[-10:]:
        log(f"[{year}]   error: {e[:200]}")
    return result


def remove_empty_tile_dirs(year: int, root: str) -> None:
    """The merge deletes tile files but leaves their (empty) folders."""
    year_dir = Path(root) / str(year)
    removed = 0
    for d in year_dir.glob("lake_*"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
            removed += 1
    if removed:
        log(f"[{year}] removed {removed} empty tile folders")


# ── Threads ───────────────────────────────────────────────────────────────


def download_worker(years, root, ready: queue.Queue) -> None:
    for i, year in enumerate(years):
        t0 = time.time()
        try:
            summary.setdefault(year, {})["download"] = download(year, root, first=(i == 0))
        except Exception as exc:
            log(f"[{year}] DOWNLOAD crashed: {exc}")
            summary.setdefault(year, {})["download"] = {"status": f"crashed: {exc}"}
        summary[year]["download_min"] = round((time.time() - t0) / 60)
        ready.put(year)
    ready.put(None)


def processing_worker(ready: queue.Queue, root: str) -> None:
    while True:
        year = ready.get()
        if year is None:
            return
        t0 = time.time()
        for name in ("merge", "embeddings", "features"):
            try:
                summary[year][name] = run_step(name, year)
            except Exception as exc:
                log(f"[{year}] {name.upper()} crashed: {exc}")
                summary[year][name] = {"status": f"crashed: {exc}"}
            if name == "merge":
                remove_empty_tile_dirs(year, root)
        summary[year]["process_min"] = round((time.time() - t0) / 60)
        log(f"[{year}] YEAR COMPLETE (processing {summary[year]['process_min']} min)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", type=int, nargs="+", required=True)
    ap.add_argument("--root", required=True, help="Storage root; files go to <root>/<year>/")
    args = ap.parse_args()

    log(f"Pipeline: years {args.years} → {args.root}")
    ready: queue.Queue = queue.Queue()
    threads = [
        threading.Thread(target=download_worker, args=(args.years, args.root, ready), name="download"),
        threading.Thread(target=processing_worker, args=(ready, args.root), name="processing"),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log("ALL DONE — summary")
    for year in args.years:
        s = summary.get(year, {})
        line = [f"{year}:"]
        for step, keys in (
            ("download", ("success", "skipped", "failed")),
            ("merge", ("success", "skipped", "failed")),
            ("embeddings", ("success", "skipped", "failed")),
            ("features", ("processed", "skipped", "failed")),
        ):
            p = s.get(step, {})
            line.append(f"{step}[{p.get('status')}: " + " ".join(f"{k}={p.get(k)}" for k in keys) + "]")
        line.append(f"dl {s.get('download_min')}m, proc {s.get('process_min')}m")
        log(" ".join(line))


if __name__ == "__main__":
    main()
