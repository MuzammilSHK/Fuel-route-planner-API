from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from planner.corridor import station_index
from planner.geo import haversine_miles
from planner.openroute import Route
from stations.models import FuelStation

from .helpers import add_place, add_station

ROUTE = [(-100.0, 38.0), (-95.0, 38.0)]
ROUTE_MILES = float(haversine_miles(38.0, -100.0, 38.0, -95.0))
TRIP = {"start": "Alpha, KS", "finish": "Omega, KS"}


def fake_route(start, finish):
    return Route(ROUTE, ROUTE_MILES, ROUTE_MILES * 60), False


@mock.patch("planner.services.get_route", side_effect=fake_route)
class RoutePlanApiTests(TestCase):
    def setUp(self):
        cache.clear()
        station_index.cache_clear()
        self.addCleanup(station_index.cache_clear)
        add_place("Alpha", "KS", 38.0, -100.0)
        add_place("Omega", "KS", 38.0, -95.0)
        add_station(1, "3.20", 38.0, -99.9, name="ALPHA FUEL")
        add_station(2, "2.50", 38.0, -98.0, name="CHEAP MIDWAY")
        add_station(3, "3.50", 38.0, -96.5, name="PRICEY EAST")

    def plan(self, **params):
        return self.client.get(reverse("route-plan"), params)

    def test_returns_stops_totals_route_and_map_link(self, get_route):
        response = self.plan(**TRIP)
        self.assertEqual(response.status_code, 200)
        plan = response.json()

        stops = plan["fuel_stops"]
        self.assertEqual(
            [stop["name"] for stop in stops], ["ALPHA FUEL", "CHEAP MIDWAY"]
        )
        summary = plan["summary"]
        self.assertAlmostEqual(summary["total_gallons"], ROUTE_MILES / 10, delta=0.02)
        spent = summary["starting_fuel_cost"] + sum(stop["cost"] for stop in stops)
        self.assertAlmostEqual(summary["total_cost"], spent, places=2)

        self.assertEqual(plan["start"]["resolved_by"], "places")
        self.assertEqual(plan["meta"]["external_api_calls"], 1)
        self.assertEqual(plan["route"]["type"], "LineString")
        self.assertIn(
            "/api/route/map/?start=Alpha%2C+KS&finish=Omega%2C+KS", plan["map_url"]
        )

    def test_missing_finish_is_a_400(self, get_route):
        response = self.plan(start="Alpha, KS")
        self.assertEqual(response.status_code, 400)
        self.assertIn("finish", response.json())
        get_route.assert_not_called()

    def test_same_start_and_finish_is_a_400(self, get_route):
        response = self.plan(start="Alpha, KS", finish="alpha, ks")
        self.assertEqual(response.status_code, 400)
        self.assertIn("must be different", response.json()["finish"][0])

    def test_coordinates_outside_the_usa_are_a_400(self, get_route):
        response = self.plan(start="51.5074,-0.1278", finish="Omega, KS")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not inside the USA", response.json()["detail"])

    def test_a_stretch_without_fuel_is_a_422(self, get_route):
        get_route.side_effect = None
        get_route.return_value = (
            Route([(-100.0, 38.0), (-85.0, 38.0)], 820.0, 50000.0),
            False,
        )
        response = self.plan(**TRIP)
        self.assertEqual(response.status_code, 422)
        self.assertIn("No fuel station between", response.json()["detail"])

    def test_missing_station_data_is_a_503(self, get_route):
        FuelStation.objects.all().delete()
        response = self.plan(**TRIP)
        self.assertEqual(response.status_code, 503)
        self.assertIn("import_stations", response.json()["detail"])

    def test_map_page_shows_the_plan(self, get_route):
        response = self.client.get(reverse("route-map"), TRIP)
        self.assertContains(response, "CHEAP MIDWAY")
        self.assertContains(response, 'id="plan-data"')

    def test_map_page_explains_bad_input(self, get_route):
        response = self.client.get(reverse("route-map"), {"start": "Alpha, KS"})
        self.assertContains(
            response, "finish: This field is required.", status_code=400
        )
