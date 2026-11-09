import csv
from decimal import ROUND_HALF_UP, Decimal

PRICE_STEP = Decimal("0.001")


def tidy(value):
    return " ".join(value.split())


def read_price_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            yield {
                "opis_id": int(row["OPIS Truckstop ID"]),
                "name": tidy(row["Truckstop Name"]),
                "address": tidy(row["Address"]),
                "city": tidy(row["City"]),
                "state": tidy(row["State"]).upper(),
                "rack_id": int(row["Rack ID"]),
                "price": Decimal(row["Retail Price"].strip()).quantize(
                    PRICE_STEP, ROUND_HALF_UP
                ),
            }


def cheapest_per_station(rows):
    stations = {}
    for row in rows:
        current = stations.get(row["opis_id"])
        if current is None or row["price"] < current["price"]:
            stations[row["opis_id"]] = row
    return list(stations.values())
