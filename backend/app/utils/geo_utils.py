import math
from typing import Tuple


_EARTH_RADIUS_KM = 6_371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return _EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bbox_from_center(
    lat: float, lon: float, size_km: float = 5.0
) -> Tuple[float, float, float, float]:
    """
    Return (min_lat, min_lon, max_lat, max_lon) for a square grid cell
    centred at (lat, lon) with the given side length in km.
    """
    half = size_km / 2.0
    dlat = half / _EARTH_RADIUS_KM * (180.0 / math.pi)
    dlon = half / (_EARTH_RADIUS_KM * math.cos(math.radians(lat))) * (180.0 / math.pi)
    return lat - dlat, lon - dlon, lat + dlat, lon + dlon


def bbox_to_wkt(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> str:
    """Convert a bounding box to a WKT POLYGON string (EPSG:4326)."""
    return (
        f"POLYGON(("
        f"{min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, "
        f"{min_lon} {min_lat}))"
    )


def center_to_grid_wkt(lat: float, lon: float, size_km: float = 5.0) -> str:
    """Return the WKT polygon for a 5 km × 5 km cell centred at (lat, lon)."""
    return bbox_to_wkt(*bbox_from_center(lat, lon, size_km))
