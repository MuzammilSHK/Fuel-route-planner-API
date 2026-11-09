import csv
import io
import tempfile
import zipfile
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from stations.models import FuelStation, Place
from stations.places import place_key

PRICE_HEADER = [
    "OPIS Truckstop ID",
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Rack ID",
    "Retail Price",
]
CENSUS_HEADER = (
    "USPS|GEOID|GEOIDFQ|ANSICODE|NAME|LSAD|FUNCSTAT|ALAND|AWATER|"
    "ALAND_SQMI|AWATER_SQMI|INTPTLAT|INTPTLONG"
)


def price_row(opis_id, name, city, state, price, address="I-44, EXIT 283"):
    return [opis_id, name, address, city, state, "307", price]


class ImportStationsTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.csv_path = Path(folder.name) / "prices.csv"
        for name, state, latitude, longitude in (
            ("Big Cabin", "OK", 36.54, -95.23),
            ("Gila Bend", "AZ", 32.97, -112.72),
        ):
            Place.objects.create(
                name=name,
                state=state,
                lookup_key=place_key(name),
                latitude=latitude,
                longitude=longitude,
            )

    def run_import(self, rows):
        with open(self.csv_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            writer.writerow(PRICE_HEADER)
            writer.writerows(rows)
        output = io.StringIO()
        with self.settings(FUEL_PRICES_CSV=self.csv_path):
            call_command("import_stations", stdout=output)
        return output.getvalue()

    def test_merges_duplicates_and_keeps_the_cheapest_price(self):
        output = self.run_import(
            [
                price_row(
                    "7", "WOODSHED OF BIG CABIN", "Big Cabin   ", "OK", "3.00733333"
                ),
                price_row(
                    "20", "PILOT TRAVEL CENTER #1243", "Gila Bend", "AZ", "3.999"
                ),
                price_row(
                    "20", "PILOT #1243", "Gila Bend", "AZ", "3.899", "I-8,  EXIT 119"
                ),
            ]
        )
        self.assertIn("Imported 2 stations", output)
        pilot = FuelStation.objects.get(opis_id=20)
        self.assertEqual((pilot.name, str(pilot.price)), ("PILOT #1243", "3.899"))
        self.assertEqual(pilot.address, "I-8, EXIT 119")
        cabin = FuelStation.objects.get(opis_id=7)
        self.assertEqual((cabin.city, str(cabin.price)), ("Big Cabin", "3.007"))
        self.assertEqual((cabin.latitude, cabin.longitude), (36.54, -95.23))

    def test_skips_canada_and_towns_it_cannot_place(self):
        output = self.run_import(
            [
                price_row("7", "WOODSHED OF BIG CABIN", "Big Cabin", "OK", "3.007"),
                price_row("900", "FLYING J", "Calgary", "AB", "4.454"),
                price_row("901", "NOWHERE FUEL", "Nowhere", "TX", "3.10"),
            ]
        )
        self.assertEqual(
            list(FuelStation.objects.values_list("opis_id", flat=True)), [7]
        )
        self.assertIn("1 outside the US", output)
        self.assertIn("Skipped NOWHERE FUEL in Nowhere, TX", output)

    def test_running_it_twice_does_not_duplicate_rows(self):
        rows = [price_row("7", "WOODSHED OF BIG CABIN", "Big Cabin", "OK", "3.007")]
        self.run_import(rows)
        self.run_import(rows)
        self.assertEqual(FuelStation.objects.count(), 1)

    def test_asks_for_places_first(self):
        Place.objects.all().delete()
        with self.assertRaisesMessage(CommandError, "run import_places first"):
            self.run_import([])


class ImportPlacesTests(TestCase):
    def test_loads_census_names_aliases_and_extra_places(self):
        with tempfile.TemporaryDirectory() as folder:
            census = Path(folder) / "places.zip"
            with zipfile.ZipFile(census, "w") as archive:
                archive.writestr(
                    "places.txt",
                    "\n".join(
                        [
                            CENSUS_HEADER,
                            "OK|1|x|x|Big Cabin town|43|A|1|0|1|0|36.537|-95.229",
                            "ID|2|x|x|Boise City city|25|A|1|0|1|0|43.598|-116.231",
                            "PR|3|x|x|Adjuntas zona urbana|62|S|1|0|1|0|18.163|-66.723",
                        ]
                    ),
                )
            extra = Path(folder) / "extra_places.csv"
            extra.write_text(
                "state,name,latitude,longitude\nGA,Ellenwood,33.61,-84.288\n",
                encoding="utf-8",
            )
            with self.settings(CENSUS_PLACES_ZIP=census, EXTRA_PLACES_CSV=extra):
                call_command("import_places", stdout=io.StringIO())

        self.assertEqual(
            set(Place.objects.values_list("state", "lookup_key")),
            {
                ("OK", "bigcabin"),
                ("ID", "boisecity"),
                ("ID", "boise"),
                ("GA", "ellenwood"),
            },
        )
        self.assertEqual(Place.objects.get(lookup_key="boise").name, "Boise")
