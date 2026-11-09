import csv
import time

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from stations.fuel_prices import read_price_rows
from stations.models import Place
from stations.places import STATE_NAMES, place_key

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class Command(BaseCommand):
    help = (
        "Look up station towns that are missing from the Place table on "
        "OpenStreetMap and append them to extra_places.csv."
    )

    def handle(self, *args, **options):
        known = set(Place.objects.values_list("state", "lookup_key"))
        missing = {}
        for row in read_price_rows(settings.FUEL_PRICES_CSV):
            key = (row["state"], place_key(row["city"]))
            if row["state"] in STATE_NAMES and key not in known:
                missing.setdefault(key, row["city"])

        self.stdout.write(f"Looking up {len(missing)} towns, one per second...")
        session = requests.Session()
        session.headers["User-Agent"] = "fuel-route-planner/1.0"
        path = settings.EXTRA_PLACES_CSV
        new_file = not path.exists()
        found = 0

        with open(path, "a", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            if new_file:
                writer.writerow(["state", "name", "latitude", "longitude"])
            for (state, lookup_key), city in sorted(missing.items()):
                time.sleep(1)
                try:
                    coordinates = self.search(session, city, state)
                except requests.RequestException as error:
                    message = f"Lookup failed for {city}, {state}: {error}"
                    self.stdout.write(self.style.WARNING(message))
                    continue
                if coordinates is None:
                    self.stdout.write(self.style.WARNING(f"Not found: {city}, {state}"))
                    continue
                latitude, longitude = coordinates
                writer.writerow([state, city, latitude, longitude])
                Place.objects.create(
                    state=state,
                    lookup_key=lookup_key,
                    name=city,
                    latitude=latitude,
                    longitude=longitude,
                )
                found += 1

        self.stdout.write(self.style.SUCCESS(f"Found {found} of {len(missing)} towns."))

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
