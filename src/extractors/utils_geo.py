thonimport math
from typing import Iterable, Tuple

def haversine_distance_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """
    Compute the great-circle distance between two points on Earth (in kilometers).

    Uses the haversine formula and assumes a spherical Earth with radius 6371km.
    """
    radius_km = 6371.0

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return radius_km * c

def compute_centroid(coords: Iterable[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Compute a simple arithmetic centroid (mean latitude and longitude)
    from an iterable of (lat, lon) pairs.

    Returns (lat, lon) in degrees. Raises ValueError if no coordinates are provided.
    """
    total_lat = 0.0
    total_lon = 0.0
    count = 0

    for lat, lon in coords:
        total_lat += float(lat)
        total_lon += float(lon)
        count += 1

    if count == 0:
        raise ValueError("compute_centroid() requires at least one coordinate")

    return total_lat / count, total_lon / count