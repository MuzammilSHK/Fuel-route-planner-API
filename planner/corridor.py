from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from stations.models import FuelStation

from .exceptions import StationsNotLoaded
from .geo import chord_to_miles, haversine_miles, miles_to_chord, unit_vectors

STATION_FIELDS = (
    "opis_id",
    "name",
    "address",
    "city",
    "state",
    "price",
    "latitude",
    "longitude",
)


@dataclass(frozen=True)
class StationIndex:
    records: list
    prices: np.ndarray
    vectors: np.ndarray


@dataclass(frozen=True)
class RouteLine:
    miles: np.ndarray
    latitudes: np.ndarray
    longitudes: np.ndarray

    @property
    def coordinates(self):
        return np.column_stack((self.longitudes, self.latitudes)).round(5).tolist()


@dataclass(frozen=True)
class NearbyStations:
    records: list
    miles: np.ndarray
    offsets: np.ndarray
    prices: np.ndarray


@lru_cache(maxsize=1)
def station_index():
    records = list(FuelStation.objects.values(*STATION_FIELDS))
    if not records:
        raise StationsNotLoaded()
    latitudes = np.array([record["latitude"] for record in records])
    longitudes = np.array([record["longitude"] for record in records])
    prices = np.array([float(record["price"]) for record in records])
    return StationIndex(records, prices, unit_vectors(latitudes, longitudes))


def resample_route(coordinates, route_miles, step_miles=0.5):
    points = np.asarray(coordinates, dtype=float)
    longitudes, latitudes = points[:, 0], points[:, 1]
    segments = haversine_miles(
        latitudes[:-1], longitudes[:-1], latitudes[1:], longitudes[1:]
    )
    travelled = np.concatenate(([0.0], np.cumsum(segments)))
    if travelled[-1] > 0:
        travelled *= route_miles / travelled[-1]

    miles = np.append(np.arange(0.0, route_miles, step_miles), route_miles)
    return RouteLine(
        miles=miles,
        latitudes=np.interp(miles, travelled, latitudes),
        longitudes=np.interp(miles, travelled, longitudes),
    )


def stations_near(line, max_offset_miles):
    stations = station_index()
    samples = unit_vectors(line.latitudes, line.longitudes)
    chords, nearest = cKDTree(samples).query(
        stations.vectors, distance_upper_bound=miles_to_chord(max_offset_miles)
    )

    found = np.flatnonzero(np.isfinite(chords))
    miles = line.miles[nearest[found]]
    order = np.lexsort((stations.prices[found], miles))
    found, miles = found[order], miles[order]
    return NearbyStations(
        records=[stations.records[i] for i in found],
        miles=miles,
        offsets=chord_to_miles(chords[found]),
        prices=stations.prices[found],
    )
