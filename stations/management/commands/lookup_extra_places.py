import csv
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from stations.fuel_prices import read_price_rows
from stations.models import Place
from stations.places import STATE_NAMES, place_key

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
SNAP_BATCH = 2500
MAX_MOVE_DEGREES = 1


class Command(BaseCommand):
    help = (
        "Look up on OpenStreetMap the station towns that the Place table lacks "
        "and the towns it puts away from any road, then save them to "
        "extra_places.csv."
    )

    def handle(self, *args, **options):
        places = {
            (place.state, place.lookup_key): place for place in Place.objects.all()
        }
        towns = self.towns_to_look_up(places)
        self.stdout.write(f"Looking up {len(towns)} towns, one per second...")
        saved = self.save(self.look_up(towns), places)
        self.stdout.write(self.style.SUCCESS(f"Saved {saved} of {len(towns)} towns."))

    def towns_to_look_up(self, places):
        points = [(place.latitude, place.longitude) for place in places.values()]
        checked = zip(places.items(), self.off_road(points), strict=True)
        towns = {key: place.name for (key, place), off_road in checked if off_road}
        for row in read_price_rows(settings.FUEL_PRICES_CSV):
            key = (row["state"], place_key(row["city"]))
            if row["state"] in STATE_NAMES and key not in places:
                towns.setdefault(key, row["city"])
        return towns

    def look_up(self, towns):
        session = requests.Session()
        session.headers["User-Agent"] = "fuel-route-planner/1.0"
        found = {}
        for (state, lookup_key), name in sorted(towns.items()):
            time.sleep(1)
            try:
                point = self.search(session, name, state)
            except requests.RequestException as error:
                self.warn(f"Lookup failed for {name}, {state}: {error}")
                continue
            if point is None:
                self.warn(f"Not found: {name}, {state}")
                continue
            found[(state, lookup_key)] = (name, point)
        return found

    def save(self, found, places):
        path = settings.EXTRA_PLACES_CSV
        new_file = not path.exists()
        points = [point for name, point in found.values()]
        checked = zip(found.items(), self.off_road(points), strict=True)
        saved = 0
        with open(path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["state", "name", "latitude", "longitude"])
            for (key, (name, point)), off_road in checked:
                state, lookup_key = key
                if off_road or self.moved_too_far(places.get(key), point):
                    self.warn(f"Not usable: {name}, {state} at {point}")
                    continue
                latitude, longitude = point
                writer.writerow([state, name, latitude, longitude])
                Place.objects.update_or_create(
                    state=state,
                    lookup_key=lookup_key,
                    defaults={
                        "name": name,
                        "latitude": latitude,
                        "longitude": longitude,
                    },
                )
                saved += 1
        return saved

    def off_road(self, points):
        url = (
            f"{settings.ORS_BASE_URL}/openrouteservice/v2/snap/"
            f"{settings.ORS_PROFILE}/json"
        )
        flags = []
        for start in range(0, len(points), SNAP_BATCH):
            batch = points[start : start + SNAP_BATCH]
            response = requests.post(
                url,
                headers={"Authorization": settings.ORS_API_KEY},
                json={
                    "locations": [
                        [longitude, latitude] for latitude, longitude in batch
                    ],
                    "radius": settings.ORS_SNAP_RADIUS_METERS,
                },
                timeout=120,
            )
            response.raise_for_status()
            flags += [snapped is None for snapped in response.json()["locations"]]
        return flags

    def moved_too_far(self, place, point):
        if place is None:
            return False
        latitude, longitude = point
        return (
            abs(place.latitude - latitude) > MAX_MOVE_DEGREES
            or abs(place.longitude - longitude) > MAX_MOVE_DEGREES
        )

    def search(self, session, city, state):
        params = {
            "q": f"{city}, {STATE_NAMES[state]}",
            "countrycodes": "us",
            "featureType": "settlement",
            "addressdetails": 1,
            "format": "jsonv2",
            "limit": 3,
        }
        for attempt in range(1, 4):
            try:
                response = session.get(NOMINATIM_URL, params=params, timeout=20)
                response.raise_for_status()
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(5 * attempt)
        for result in response.json():
            if result.get("address", {}).get("state") == STATE_NAMES[state]:
                return round(float(result["lat"]), 6), round(float(result["lon"]), 6)
        return None

    def warn(self, message):
        self.stdout.write(self.style.WARNING(message))
