import hashlib
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import RouteNotFound, RoutingUnavailable
from .geo import decode_polyline

PRECISE_LAYERS = (
    "address,venue,street,neighbourhood,borough,localadmin,locality,postalcode"
)

session = requests.Session()


@dataclass(frozen=True)
class Route:
    coordinates: list
    miles: float
    seconds: float


def get_route(start, finish):
    key = cache_key(
        "route",
        settings.ORS_PROFILE,
        f"{start.latitude:.5f},{start.longitude:.5f}",
        f"{finish.latitude:.5f},{finish.longitude:.5f}",
    )
    route = cache.get(key)
    if route is not None:
        return route, True

    response = call(
        "POST",
        f"/openrouteservice/v2/directions/{settings.ORS_PROFILE}/json",
        json={
            "coordinates": [
                [start.longitude, start.latitude],
                [finish.longitude, finish.latitude],
            ],
            "units": "mi",
            "instructions": False,
            "geometry_simplify": True,
            "radiuses": [5000, 5000],
            "options": {"avoid_borders": "all"},
        },
    )
    if not response.ok:
        raise RouteNotFound(error_message(response) or None)

    data = response.json()["routes"][0]
    summary = data["summary"]
    route = Route(
        coordinates=decode_polyline(data["geometry"]),
        miles=summary.get("distance", 0.0),
        seconds=summary.get("duration", 0.0),
    )
    cache.set(key, route, settings.ORS_CACHE_SECONDS)
    return route, False


def geocode(text):
    key = cache_key("geocode", text.lower())
    cached = cache.get(key)
    if cached is not None:
        return cached or None, True

    response = call(
        "GET",
        "/pelias/v1/search",
        params={
            "text": text,
            "boundary.country": "USA",
            "layers": PRECISE_LAYERS,
            "size": 1,
        },
    )
    if not response.ok:
        raise RoutingUnavailable(error_message(response) or None)

    result = {}
    features = response.json().get("features") or []
    if features:
        longitude, latitude = features[0]["geometry"]["coordinates"][:2]
        label = features[0]["properties"].get("label", text)
        result = {"label": label, "latitude": latitude, "longitude": longitude}
    cache.set(key, result, settings.ORS_CACHE_SECONDS)
    return result or None, False


def call(method, path, **kwargs):
    if not settings.ORS_API_KEY:
        raise RoutingUnavailable("ORS_API_KEY is not set, add it to the .env file.")
    try:
        response = session.request(
            method,
            settings.ORS_BASE_URL + path,
            headers={"Authorization": settings.ORS_API_KEY},
            timeout=settings.ORS_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as error:
        raise RoutingUnavailable() from error
    if response.status_code in (401, 403):
        raise RoutingUnavailable("The routing service rejected the API key.")
    if response.status_code == 429:
        raise RoutingUnavailable("The routing quota is used up, try again later.")
    if response.status_code >= 500:
        raise RoutingUnavailable()
    return response


def error_message(response):
    try:
        error = response.json().get("error")
    except ValueError:
        return ""
    if isinstance(error, dict):
        return error.get("message", "")
    return str(error or "")


def cache_key(*parts):
    return "ors:" + hashlib.sha256("|".join(parts).encode()).hexdigest()
