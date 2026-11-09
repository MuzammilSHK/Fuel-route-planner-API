from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stations.fuel_prices import cheapest_per_station, read_price_rows
from stations.models import FuelStation, Place
from stations.places import STATE_NAMES, place_key


class Command(BaseCommand):
    help = "Load the fuel price CSV into the FuelStation table."

    def handle(self, *args, **options):
        locations = {
            (state, lookup_key): (latitude, longitude)
            for state, lookup_key, latitude, longitude in Place.objects.values_list(
                "state", "lookup_key", "latitude", "longitude"
            )
        }
        if not locations:
            raise CommandError("The Place table is empty, run import_places first.")

        rows = list(read_price_rows(settings.FUEL_PRICES_CSV))
        us_rows = [row for row in rows if row["state"] in STATE_NAMES]
        records = cheapest_per_station(us_rows)

        stations = []
        unplaced = []
        for record in records:
            location = locations.get((record["state"], place_key(record["city"])))
            if location is None:
                unplaced.append(record)
                continue
            latitude, longitude = location
            stations.append(
                FuelStation(**record, latitude=latitude, longitude=longitude)
            )

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations)

        self.stdout.write(
            f"Read {len(rows):,} rows: {len(rows) - len(us_rows):,} outside the US, "
            f"{len(records):,} unique US stations after merging duplicates."
        )
        for record in unplaced:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {record['name']} in {record['city']}, {record['state']}: "
                    "town not found"
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Imported {len(stations):,} stations."))
