import time

from django.conf import settings

from .corridor import resample_route, stations_near
from .exceptions import SamePlace
from .locations import resolve_location
from .openroute import get_route
from .optimizer import plan_fuel_stops


def plan_trip(start, finish):
    started = time.perf_counter()
    origin = resolve_location(start)
    destination = resolve_location(finish)
    if origin.point == destination.point:
        raise SamePlace()
    route, route_cached = get_route(origin, destination)
    routed = time.perf_counter()

    line = resample_route(route.coordinates, route.miles)
    nearby = stations_near(line, settings.MAX_MILES_OFF_ROUTE)
    first_stop, purchases = plan_fuel_stops(
        nearby.miles,
        nearby.prices,
        trip_miles=route.miles,
        tank_miles=settings.VEHICLE_RANGE_MILES,
        mpg=settings.VEHICLE_MILES_PER_GALLON,
        first_stop_within=settings.FIRST_STOP_WITHIN_MILES,
        stop_penalty=settings.STOP_PENALTY_DOLLARS,
    )
    stops = [
        stop_details(number, nearby, purchase)
        for number, purchase in enumerate(purchases, start=1)
    ]

    starting_miles = float(nearby.miles[first_stop])
    starting_gallons = round(starting_miles / settings.VEHICLE_MILES_PER_GALLON, 2)
    starting_cost = round(starting_gallons * float(nearby.prices[first_stop]), 2)
    total_gallons = starting_gallons + sum(stop["gallons"] for stop in stops)
    total_cost = starting_cost + sum(stop["cost"] for stop in stops)
    api_calls = sum(location.source == "geocoder" for location in (origin, destination))

    return {
        "start": location_details(start, origin),
        "finish": location_details(finish, destination),
        "summary": {
            "distance_miles": round(route.miles, 1),
            "duration_hours": round(route.seconds / 3600, 1),
            "fuel_stops": len(stops),
            "total_gallons": round(total_gallons, 2),
            "total_cost": round(total_cost, 2),
            "average_price_per_gallon": (
                round(total_cost / total_gallons, 3) if total_gallons else 0.0
            ),
            "starting_fuel_gallons": starting_gallons,
            "starting_fuel_cost": starting_cost,
            "stations_near_route": len(nearby.records),
            "vehicle_range_miles": settings.VEHICLE_RANGE_MILES,
            "miles_per_gallon": settings.VEHICLE_MILES_PER_GALLON,
        },
        "fuel_stops": stops,
        "meta": {
            "external_api_calls": api_calls + (0 if route_cached else 1),
            "routing_ms": round((routed - started) * 1000),
            "planning_ms": round((time.perf_counter() - routed) * 1000),
        },
        "route": {"type": "LineString", "coordinates": line.coordinates},
    }


def stop_details(number, nearby, purchase):
    record = nearby.records[purchase.index]
    price = float(nearby.prices[purchase.index])
    gallons = round(purchase.gallons, 2)
    return {
        "stop": number,
        "opis_id": record["opis_id"],
        "name": record["name"],
        "address": record["address"],
        "city": record["city"],
        "state": record["state"],
        "latitude": record["latitude"],
        "longitude": record["longitude"],
        "mile_marker": round(float(nearby.miles[purchase.index]), 1),
        "miles_off_route": round(float(nearby.offsets[purchase.index]), 1),
        "price_per_gallon": price,
        "gallons": gallons,
        "cost": round(gallons * price, 2),
    }


def location_details(query, location):
    return {
        "query": query,
        "label": location.label,
        "latitude": round(location.latitude, 5),
        "longitude": round(location.longitude, 5),
        "resolved_by": location.source,
    }
