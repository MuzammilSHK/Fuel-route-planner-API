from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import Place
from stations.places import (
    census_aliases,
    clean_census_name,
    place_key,
    read_census_places,
    read_extra_places,
)


class Command(BaseCommand):
    help = "Load US towns and their coordinates into the Place table."

    def handle(self, *args, **options):
        places = {}
        aliases = {}
        for row in read_census_places(settings.CENSUS_PLACES_ZIP):
            state = row["USPS"]
            name = clean_census_name(row["NAME"])
            latitude, longitude = float(row["INTPTLAT"]), float(row["INTPTLONG"])
            places.setdefault((state, place_key(name)), (name, latitude, longitude))
            for alias in census_aliases(row["NAME"], name):
                key = (state, place_key(alias))
                aliases.setdefault(key, (alias, latitude, longitude))
        census_count = len(places)

        for row in read_extra_places(settings.EXTRA_PLACES_CSV):
            location = (row["name"], float(row["latitude"]), float(row["longitude"]))
            places.setdefault((row["state"], place_key(row["name"])), location)
        extra_count = len(places) - census_count

        for key, location in aliases.items():
            places.setdefault(key, location)
        alias_count = len(places) - census_count - extra_count

        with transaction.atomic():
            Place.objects.all().delete()
            Place.objects.bulk_create(
                Place(
                    state=state,
                    lookup_key=lookup_key,
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                )
                for (state, lookup_key), (name, latitude, longitude) in places.items()
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(places):,} places: {census_count:,} from the Census "
                f"file, {extra_count:,} from {settings.EXTRA_PLACES_CSV.name}, "
                f"{alias_count:,} alternate names."
            )
        )
