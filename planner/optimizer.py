from dataclasses import dataclass

import numpy as np

from .exceptions import FuelGap


@dataclass(frozen=True)
class Purchase:
    index: int
    gallons: float


def plan_fuel_stops(
    miles, prices, trip_miles, tank_miles, mpg, first_stop_within, stop_penalty
):
    stops = choose_stops(
        miles, prices, trip_miles, tank_miles, mpg, first_stop_within, stop_penalty
    )
    purchases = [
        Purchase(int(stops[position]), fuel / mpg)
        for position, fuel in fill_amounts(
            miles[stops], prices[stops], trip_miles, tank_miles
        )
    ]
    return int(stops[0]), purchases


def choose_stops(
    miles, prices, trip_miles, tank_miles, mpg, first_stop_within, stop_penalty
):
    if len(miles) == 0:
        raise FuelGap("The fuel price list has no station along this route.")
    if miles[0] > tank_miles:
        raise FuelGap(gap_message(miles, trip_miles, tank_miles))

    cost_per_mile = prices / mpg
    best = np.full(len(miles), np.inf)
    previous = np.full(len(miles), -1)
    first = miles <= miles[0] + first_stop_within
    best[first] = cost_per_mile[first] * miles[first] + stop_penalty
    finish_cost, last_stop = np.inf, -1

    for stop in range(len(miles)):
        if np.isinf(best[stop]):
            continue
        if miles[stop] + tank_miles >= trip_miles:
            total = best[stop] + cost_per_mile[stop] * (trip_miles - miles[stop])
            if total < finish_cost:
                finish_cost, last_stop = total, stop
        end = np.searchsorted(miles, miles[stop] + tank_miles, side="right")
        ahead = np.arange(stop + 1, end)
        leg_cost = cost_per_mile[stop] * (miles[ahead] - miles[stop])
        candidate = best[stop] + leg_cost + stop_penalty
        better = candidate < best[ahead]
        best[ahead[better]] = candidate[better]
        previous[ahead[better]] = stop

    if last_stop < 0:
        raise FuelGap(gap_message(miles, trip_miles, tank_miles))

    chosen = []
    while last_stop >= 0:
        chosen.append(last_stop)
        last_stop = previous[last_stop]
    return np.array(chosen[::-1])


def fill_amounts(miles, prices, trip_miles, tank_miles):
    positions = np.append(miles, trip_miles)
    costs = np.append(prices, -1.0)
    finish = len(positions) - 1
    current, fuel, purchases = 0, 0.0, []

    while current != finish:
        here = positions[current]
        end = np.searchsorted(positions, here + tank_miles, side="right")
        ahead = np.arange(current + 1, end)
        cheaper = ahead[costs[ahead] < costs[current]]
        if cheaper.size:
            target = cheaper[0]
            bought = max(positions[target] - here - fuel, 0.0)
        else:
            target = ahead[costs[ahead] == costs[ahead].min()][-1]
            bought = tank_miles - fuel
        if bought > 0:
            purchases.append((current, bought))
        fuel += bought - (positions[target] - here)
        current = target

    return purchases


def gap_message(miles, trip_miles, tank_miles):
    points = np.concatenate(([0.0], miles, [trip_miles]))
    widest = int(np.argmax(np.diff(points)))
    return (
        f"The fuel price list has no station between mile {points[widest]:.0f} and "
        f"mile {points[widest + 1]:.0f} of this route, which is more than the "
        f"{tank_miles:g}-mile range."
    )
