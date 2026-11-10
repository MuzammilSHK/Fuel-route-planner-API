from unittest import mock

from django.test import TestCase

from planner.exceptions import LocationNotFound
from planner.locations import inside_usa, resolve_location
from stations.tests.helpers import add_place

WHITE_HOUSE = "1600 Pennsylvania Ave NW, Washington, DC"


class ResolveLocationTests(TestCase):
    def setUp(self):
        add_place("Chicago", "IL", 41.837, -87.685)
        add_place("St. Louis", "MO", 38.636, -90.245)
        add_place("Springfield", "IL", 39.791, -89.645)

    def test_city_and_state_come_from_the_places_table(self):
        location = resolve_location("Chicago, IL")
        self.assertEqual((location.label, location.source), ("Chicago, IL", "places"))
        self.assertEqual((location.latitude, location.longitude), (41.837, -87.685))

    def test_accepts_the_usual_ways_of_writing_a_town(self):
        for text in ("chicago, illinois", "Chicago, IL, USA", "Chicago, il"):
            self.assertEqual(resolve_location(text).label, "Chicago, IL")
        self.assertEqual(
            resolve_location("Saint Louis, Missouri").label, "St. Louis, MO"
        )
        self.assertEqual(
            resolve_location("Springfield, IL 62701").label, "Springfield, IL"
        )

    def test_reads_coordinates_without_any_lookup(self):
        for text in ("39.7392, -104.9903", "+39.7392,-104.9903"):
            location = resolve_location(text)
            self.assertEqual(location.source, "coordinates")
            self.assertEqual(
                (location.latitude, location.longitude), (39.7392, -104.9903)
            )

    def test_rejects_coordinates_outside_the_usa(self):
        with self.assertRaisesMessage(LocationNotFound, "not inside the USA"):
            resolve_location("51.5074, -0.1278")

    @mock.patch("planner.openroute.geocode")
    def test_falls_back_to_the_geocoder_for_street_addresses(self, geocode):
        result = {"label": WHITE_HOUSE, "latitude": 38.8977, "longitude": -77.0365}
        geocode.return_value = (result, False)
        location = resolve_location(WHITE_HOUSE)
        self.assertEqual((location.label, location.source), (WHITE_HOUSE, "geocoder"))
        geocode.assert_called_once_with(WHITE_HOUSE)

    @mock.patch("planner.openroute.geocode", return_value=(None, False))
    def test_unknown_places_get_a_clear_error(self, geocode):
        with self.assertRaisesMessage(LocationNotFound, "Could not find 'Nowhere, ZZ'"):
            resolve_location("Nowhere, ZZ")

    def test_usa_check_covers_alaska_and_hawaii_but_not_mexico(self):
        self.assertTrue(inside_usa(61.2181, -149.9003))
        self.assertTrue(inside_usa(21.3069, -157.8583))
        self.assertFalse(inside_usa(19.4326, -99.1332))
