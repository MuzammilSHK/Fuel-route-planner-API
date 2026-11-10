import csv
import io
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import requests
from django.core.management import CommandError, call_command
from django.test import TestCase

from stations.models import FuelStation, Place
from stations.places import place_key

from .helpers import add_place

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
OFF_ROAD = {
    (37.727, -123.032),
    (59.899, -151.528),
    (36.23, -112.693),
    (36.237, -112.69),
    (48.013, -122.321),
}
OPENSTREETMAP = {
    "Ellenwood, Georgia": [("33.61", "-84.288")],
    "San Francisco, California": [("37.788", "-122.408")],
    "Happy Valley, Alaska": [("51.847", "-176.654")],
    "Supai, Arizona": [("36.237", "-112.69")],
}


def price_row(opis_id, name, city, state, price, address="I-44, EXIT 283"):
    return [opis_id, name, address, city, state, "307", price]


def write_prices(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(PRICE_HEADER)
        writer.writerows(rows)


def fake_snap(url, headers, json, timeout):
    locations = [
        None if (latitude, longitude) in OFF_ROAD else {"name": "Main Street"}
        for longitude, latitude in json["locations"]
    ]
    return mock.Mock(json=mock.Mock(return_value={"locations": locations}))


def fake_search(url, params, timeout):
    state = params["q"].split(", ")[1]
    matches = [
        {"lat": latitude, "lon": longitude, "address": {"state": state}}
        for latitude, longitude in OPENSTREETMAP.get(params["q"], [])
    ]
    return mock.Mock(json=mock.Mock(return_value=matches))


class ImportStationsTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.csv_path = Path(folder.name) / "prices.csv"
        add_place("Big Cabin", "OK", 36.54, -95.23)
        add_place("Gila Bend", "AZ", 32.97, -112.72)

    def run_import(self, rows):
        write_prices(self.csv_path, rows)
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
    def run_import(self, census_rows, extra_rows=()):
        with tempfile.TemporaryDirectory() as folder:
            census = Path(folder) / "places.zip"
            with zipfile.ZipFile(census, "w") as archive:
                archive.writestr("places.txt", "\n".join([CENSUS_HEADER, *census_rows]))
            extra = Path(folder) / "extra_places.csv"
            extra.write_text(
                "\n".join(["state,name,latitude,longitude", *extra_rows]),
                encoding="utf-8",
            )
            with self.settings(CENSUS_PLACES_ZIP=census, EXTRA_PLACES_CSV=extra):
                call_command("import_places", stdout=io.StringIO())

    def location(self, state, name):
        place = Place.objects.get(state=state, lookup_key=place_key(name))
        return place.latitude, place.longitude

    def test_loads_census_names_aliases_and_extra_places(self):
        self.run_import(
            [
                "OK|1|x|x|Big Cabin town|43|A|1|0|1|0|36.537|-95.229",
                "ID|2|x|x|Boise City city|25|A|1|0|1|0|43.598|-116.231",
                "PR|3|x|x|Adjuntas zona urbana|62|S|1|0|1|0|18.163|-66.723",
            ],
            ["GA,Ellenwood,33.61,-84.288"],
        )
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

    def test_an_incorporated_town_wins_its_name_over_a_census_designated_place(self):
        self.run_import(
            [
                "PA|1|x|x|Jonestown CDP|57|S|1|0|1|0|41.12|-76.3",
                "PA|2|x|x|Jonestown borough|21|A|1|0|1|0|40.41|-76.48",
            ]
        )
        self.assertEqual(self.location("PA", "Jonestown"), (40.41, -76.48))

    def test_extra_places_move_a_census_town(self):
        self.run_import(
            ["CA|1|x|x|San Francisco city|25|A|1|0|1|0|37.727|-123.032"],
            ["CA,San Francisco,37.788,-122.408"],
        )
        self.assertEqual(self.location("CA", "San Francisco"), (37.788, -122.408))


@mock.patch("time.sleep")
@mock.patch.object(requests.Session, "get", side_effect=fake_search)
@mock.patch.object(requests, "post", side_effect=fake_snap)
class LookupExtraPlacesTests(TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.prices = Path(folder.name) / "prices.csv"
        self.extra = Path(folder.name) / "extra_places.csv"
        write_prices(
            self.prices,
            [
                price_row("7", "WOODSHED OF BIG CABIN", "Big Cabin", "OK", "3.007"),
                price_row("8", "QUIKTRIP #795", "Ellenwood", "GA", "3.10"),
            ],
        )
        add_place("Big Cabin", "OK", 36.54, -95.23)
        add_place("San Francisco", "CA", 37.727, -123.032)
        add_place("Happy Valley", "AK", 59.899, -151.528)
        add_place("Supai", "AZ", 36.23, -112.693)
        add_place("Hat Island", "WA", 48.013, -122.321)

    def run_lookup(self):
        output = io.StringIO()
        with self.settings(FUEL_PRICES_CSV=self.prices, EXTRA_PLACES_CSV=self.extra):
            call_command("lookup_extra_places", stdout=output)
        return output.getvalue()

    def location(self, state, name):
        place = Place.objects.get(state=state, lookup_key=place_key(name))
        return place.latitude, place.longitude

    def test_adds_missing_station_towns_and_moves_towns_onto_a_road(self, *mocks):
        output = self.run_lookup()
        self.assertIn("Saved 2 of 5 towns", output)
        self.assertEqual(
            self.extra.read_text(encoding="utf-8").splitlines(),
            [
                "state,name,latitude,longitude",
                "CA,San Francisco,37.788,-122.408",
                "GA,Ellenwood,33.61,-84.288",
            ],
        )
        self.assertEqual(self.location("CA", "San Francisco"), (37.788, -122.408))
        self.assertEqual(self.location("GA", "Ellenwood"), (33.61, -84.288))

    def test_ignores_matches_that_are_far_away_off_the_road_or_missing(self, *mocks):
        output = self.run_lookup()
        self.assertIn("Not usable: Happy Valley, AK", output)
        self.assertIn("Not usable: Supai, AZ", output)
        self.assertIn("Not found: Hat Island, WA", output)
        self.assertEqual(self.location("AK", "Happy Valley"), (59.899, -151.528))
        self.assertEqual(self.location("AZ", "Supai"), (36.23, -112.693))
