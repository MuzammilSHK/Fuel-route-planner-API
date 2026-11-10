from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import Place
from stations.places import (
    census_aliases,
    clean_census_name,
    incorporated_first,
    place_key,
    read_census_places,
    read_extra_places,
)


class Command(BaseCommand):
    help = "Load US towns and their coordinates into the Place table."

    def handle(self, *args, **options):
        places = {}
        aliases = {}
        census_rows = read_census_places(settings.CENSUS_PLACES_ZIP)
        for row in incorporated_first(census_rows):
            state = row["USPS"]
            name = clean_census_name(row["NAME"])
            latitude, longitude = float(row["INTPTLAT"]), float(row["INTPTLONG"])
            places.setdefault((state, place_key(name)), (name, latitude, longitude))
            for alias in census_aliases(row["NAME"], name):
                key = (state, place_key(alias))
                aliases.setdefault(key, (alias, latitude, longitude))
        census_count = len(places)

        extras = {}
        for row in read_extra_places(settings.EXTRA_PLACES_CSV):
            location = (row["name"], float(row["latitude"]), float(row["longitude"]))
            extras[(row["state"], place_key(row["name"]))] = location
        moved_count = len(extras.keys() & places.keys())
        places.update(extras)
        added_count = len(places) - census_count

        for key, location in aliases.items():
            places.setdefault(key, location)
        alias_count = len(places) - census_count - added_count

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
                f"file ({moved_count:,} moved by {settings.EXTRA_PLACES_CSV.name}), "
                f"{added_count:,} added by it, {alias_count:,} alternate names."
            )
        )
