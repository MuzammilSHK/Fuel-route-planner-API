import re
from dataclasses import dataclass

from stations.models import Place
from stations.places import STATE_NAMES, place_key

from . import openroute
from .exceptions import LocationNotFound

COORDINATES = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*$")
ZIP_CODE = re.compile(r"\s+\d{5}(?:-\d{4})?$")
STATE_CODES = {name.lower(): code for code, name in STATE_NAMES.items()}
COUNTRY_NAMES = {"us", "usa", "united states", "united states of america"}
USA_BOUNDS = [
    (24.4, 49.4, -124.9, -66.9),
    (51.2, 71.5, -179.2, -129.9),
    (18.9, 22.3, -160.3, -154.8),
]


@dataclass(frozen=True)
class Location:
    label: str
    latitude: float
    longitude: float
    source: str

    @property
    def point(self):
        return self.latitude, self.longitude


def resolve_location(text):
    coordinates = COORDINATES.match(text)
    if coordinates:
        return from_coordinates(text, float(coordinates[1]), float(coordinates[2]))

    city_state = split_city_state(text)
    if city_state:
        city, state = city_state
        place = Place.objects.filter(state=state, lookup_key=place_key(city)).first()
        if place:
            label = f"{place.name}, {place.state}"
            return Location(label, place.latitude, place.longitude, "places")

    result, cached = openroute.geocode(text)
    if result is None or not inside_usa(result["latitude"], result["longitude"]):
        raise LocationNotFound(f"Could not find '{text}' in the USA.")
    return Location(
        result["label"],
        result["latitude"],
        result["longitude"],
        "geocoder_cache" if cached else "geocoder",
    )


def from_coordinates(text, latitude, longitude):
    if not inside_usa(latitude, longitude):
        raise LocationNotFound(
            f"{text} is not inside the USA. Coordinates are read as latitude,longitude."
        )
    label = f"{latitude:.5f}, {longitude:.5f}"
    return Location(label, latitude, longitude, "coordinates")


def split_city_state(text):
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) > 2 and parts[-1].lower() in COUNTRY_NAMES:
        parts.pop()
    if len(parts) != 2:
        return None
    city, state = parts[0], ZIP_CODE.sub("", parts[1])
    code = state.upper()
    if code not in STATE_NAMES:
        code = STATE_CODES.get(state.lower())
    return (city, code) if code else None


def inside_usa(latitude, longitude):
    return any(
        south <= latitude <= north and west <= longitude <= east
        for south, north, west, east in USA_BOUNDS
    )
