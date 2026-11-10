from django.test import TestCase

from planner.corridor import resample_route, station_index, stations_near
from planner.geo import haversine_miles
from stations.tests.helpers import add_station

START = (-100.0, 40.0)
FINISH = (-99.0, 40.0)


class CorridorTests(TestCase):
    def setUp(self):
        station_index.cache_clear()
        self.addCleanup(station_index.cache_clear)
        self.route_miles = float(haversine_miles(40.0, -100.0, 40.0, -99.0))

    def test_resampled_line_has_a_point_every_half_mile(self):
        line = resample_route([START, FINISH], self.route_miles)
        self.assertAlmostEqual(line.miles[1] - line.miles[0], 0.5)
        self.assertEqual(line.miles[-1], self.route_miles)
        self.assertEqual(line.coordinates[0], [-100.0, 40.0])
        self.assertEqual(line.coordinates[-1], [-99.0, 40.0])

    def test_finds_stations_near_the_route_in_driving_order(self):
        add_station(1, "3.10", 40.0, -99.2, name="LATE")
        add_station(2, "3.30", 40.0 + 3 / 69.0, -99.5, name="THREE MILES NORTH")
        add_station(3, "2.90", 40.0 + 20 / 69.0, -99.5, name="TOO FAR")
        add_station(4, "3.50", 40.0, -99.8, name="EARLY")

        nearby = stations_near(resample_route([START, FINISH], self.route_miles), 8)

        names = [record["name"] for record in nearby.records]
        self.assertEqual(names, ["EARLY", "THREE MILES NORTH", "LATE"])
        self.assertAlmostEqual(nearby.miles[0], self.route_miles * 0.2, delta=0.5)
        self.assertAlmostEqual(nearby.offsets[1], 3.0, delta=0.1)
        self.assertEqual(list(nearby.prices), [3.5, 3.3, 3.1])
