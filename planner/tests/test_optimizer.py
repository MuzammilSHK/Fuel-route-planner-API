import numpy as np
from django.test import SimpleTestCase

from planner.exceptions import FuelGap
from planner.optimizer import plan_fuel_stops


def plan(miles, prices, trip_miles, penalty=0.0):
    return plan_fuel_stops(
        np.array(miles, dtype=float),
        np.array(prices, dtype=float),
        trip_miles,
        tank_miles=500.0,
        mpg=10.0,
        first_stop_within=25.0,
        stop_penalty=penalty,
    )


def gallons(purchases):
    return [round(purchase.gallons, 2) for purchase in purchases]


class OptimizerTests(SimpleTestCase):
    def test_fills_up_where_fuel_is_cheap_and_tops_up_later(self):
        first_stop, purchases = plan([0, 400], [3.00, 4.00], 600)
        self.assertEqual(first_stop, 0)
        self.assertEqual([purchase.index for purchase in purchases], [0, 1])
        self.assertEqual(gallons(purchases), [50.0, 10.0])

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        _, purchases = plan([0, 100], [4.00, 3.00], 400)
        self.assertEqual(gallons(purchases), [10.0, 30.0])

    def test_buys_just_enough_to_finish(self):
        _, purchases = plan([0], [3.00], 120)
        self.assertEqual(gallons(purchases), [12.0])

    def test_stop_penalty_skips_a_stop_that_only_saves_pennies(self):
        _, without_penalty = plan([0, 100], [3.00, 2.99], 400, penalty=0)
        _, with_penalty = plan([0, 100], [3.00, 2.99], 400, penalty=5)
        self.assertEqual((len(without_penalty), len(with_penalty)), (2, 1))

    def test_first_stop_is_the_best_station_near_the_start(self):
        first_stop, purchases = plan([5, 20, 60], [3.50, 3.10, 3.40], 300)
        self.assertEqual(first_stop, 1)
        self.assertEqual(gallons(purchases), [28.0])

    def test_first_stop_can_be_a_cheaper_station_just_past_a_distant_first_one(self):
        first_stop, purchases = plan([215, 221, 600], [3.95, 3.54, 3.20], 800)
        self.assertEqual(first_stop, 1)
        self.assertEqual([purchase.index for purchase in purchases], [1, 2])

    def test_a_short_trip_can_run_on_starting_fuel_alone(self):
        first_stop, purchases = plan([5, 20], [3.00, 2.00], 20)
        self.assertEqual((first_stop, purchases), (1, []))

    def test_reports_a_stretch_longer_than_the_tank_range(self):
        with self.assertRaisesMessage(FuelGap, "between mile 0 and mile 600"):
            plan([0, 600], [3.00, 3.00], 1000)

    def test_needs_at_least_one_station(self):
        with self.assertRaises(FuelGap):
            plan([], [], 300)

    def test_never_runs_dry_or_overfills_and_buys_exactly_the_trip(self):
        rng = np.random.default_rng(7)
        miles = np.sort(np.append(rng.uniform(0, 2400, 150), 3.0))
        prices = rng.uniform(2.6, 4.2, miles.size)
        first_stop, purchases = plan(miles, prices, 2400.0, penalty=5)

        position = miles[first_stop]
        fuel = 0.0
        for purchase in purchases:
            fuel -= miles[purchase.index] - position
            self.assertGreaterEqual(fuel, -1e-6)
            fuel += purchase.gallons * 10
            self.assertLessEqual(fuel, 500 + 1e-6)
            position = miles[purchase.index]
        self.assertAlmostEqual(fuel - (2400.0 - position), 0.0)

        starting_gallons = miles[first_stop] / 10
        bought = starting_gallons + sum(purchase.gallons for purchase in purchases)
        self.assertAlmostEqual(bought, 240.0)
