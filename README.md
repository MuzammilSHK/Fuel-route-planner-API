# Fuel Route Planner

A Django REST API that plans a drive between two places in the USA, chooses where to buy fuel along the way and works out what the fuel will cost.

Send a start and a finish. The API returns the driving route, the fuel stops for a truck with a 500-mile range at 10 miles per gallon, how much to buy at each stop, the total fuel bill and a link to an interactive map.

## Quick start

Python 3.12 or newer is required (Django 6.1). The commands below are for Windows; on macOS or Linux, activate with `source .venv/bin/activate` and copy the file with `cp`. If `python` is an older version on your machine, create the environment with `py -3.12 -m venv .venv` instead.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Get a free OpenRouteService key at [account.heigit.org](https://account.heigit.org) (2,000 route requests a day) and paste it after `ORS_API_KEY=` in `.env`. Then:

```bash
python manage.py migrate
python manage.py import_places
python manage.py import_stations
python manage.py runserver
```

The two import commands only read files from `data/`, so they work offline and take a few seconds.

## API

### `GET /api/route/`

| Parameter | Example |
|---|---|
| `start` | `New York, NY` |
| `finish` | `Los Angeles, CA` |

Each location can be written as:

- `City, ST` or `City, State`, optionally followed by a ZIP code or `, USA`. These are matched against a local table of 32,000 US towns, so they need no API call.
- Coordinates as `latitude,longitude`, for example `39.7392,-104.9903`.
- Any other address, which is sent to the OpenRouteService geocoder. Only specific places are accepted (an address, a venue, a street, a ZIP code or a town), so a typo such as `Chicgo, IL` returns a 400 instead of quietly starting from the middle of Illinois.

```bash
curl "http://127.0.0.1:8000/api/route/?start=New%20York,%20NY&finish=Los%20Angeles,%20CA"
```

Response, shortened:

```json
{
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=New+York%2C+NY&finish=Los+Angeles%2C+CA",
  "start": {"query": "New York, NY", "label": "New York, NY", "latitude": 40.66271, "longitude": -73.93868, "resolved_by": "places"},
  "finish": {"query": "Los Angeles, CA", "label": "Los Angeles, CA", "latitude": 34.01939, "longitude": -118.41083, "resolved_by": "places"},
  "summary": {
    "distance_miles": 2793.1,
    "duration_hours": 53.6,
    "fuel_stops": 6,
    "total_gallons": 279.31,
    "total_cost": 838.37,
    "average_price_per_gallon": 3.002,
    "starting_fuel_gallons": 1.95,
    "starting_fuel_cost": 6.04,
    "stations_near_route": 381,
    "vehicle_range_miles": 500,
    "miles_per_gallon": 10
  },
  "fuel_stops": [
    {
      "stop": 1,
      "opis_id": 52322,
      "name": "BOLLA MARKET",
      "address": "I-95, EXIT 13",
      "city": "Elizabeth",
      "state": "NJ",
      "latitude": 40.666367,
      "longitude": -74.193503,
      "mile_marker": 19.5,
      "miles_off_route": 2.9,
      "price_per_gallon": 3.099,
      "gallons": 45.15,
      "cost": 139.92
    }
  ],
  "meta": {"external_api_calls": 1, "routing_ms": 1252, "planning_ms": 23},
  "route": {"type": "LineString", "coordinates": [[-73.93872, 40.6631], [-73.9315, 40.66491]]}
}
```

- `route` is a GeoJSON line with a point every half mile, so it can be pasted straight into [geojson.io](https://geojson.io). It is about a third of the size of the raw road geometry.
- `meta.external_api_calls` shows how many requests went to OpenRouteService while answering. It is 1 for a new trip and 0 when the trip is already cached.

### `GET /api/route/map/`

Takes the same parameters and returns an HTML page with the route and the fuel stops on a map. The JSON response links to it as `map_url`. The page reuses the cached route, so opening it costs no extra API call.

### Errors

| Status | When |
|---|---|
| 400 | A parameter is missing, start and finish are the same place, or a location cannot be found in the USA |
| 422 | There is no drivable route, or the price list has no station for more than 500 miles of the route |
| 503 | The routing service is down, the key is missing or rejected, the daily quota is used up, or the stations have not been imported |

Errors come back as `{"detail": "..."}`, or as field errors for invalid parameters.

## How it works

### Preparing the data (once)

The fuel price file has no coordinates, lists many stations more than once (8,151 rows for 6,738 stations) and includes 620 rows for Canadian stations.

- `import_places` loads the US Census Gazetteer, which lists 32,000 towns with coordinates, into a `Place` table. It cleans the official names (`Boise City city` becomes `Boise City`, also reachable as `Boise`). When a town and a census-designated place in one state share a name, the town keeps it.
- `import_stations` reads the price file and drops the stations outside the US. It merges duplicate stations, keeping the lowest price, and places each station at its town's coordinates. 6,618 of the 6,626 US stations are placed this way. The 8 whose towns couldn't be matched reliably are skipped rather than guessed.

The Census file needed two repairs. Both were made once with `lookup_extra_places` and saved in `data/extra_places.csv`, which overrides the Census file:

- About 300 stations (4.5%) are in small towns the Census file doesn't list. OpenStreetMap had 219 of those towns.
- A Census coordinate is the middle of a town's legal boundary, which is not always near a road: San Francisco's is 30 miles out in the Pacific. The command checks every town against the routing service. 239 were more than 5 km from any road a truck can use, and the 61 that OpenStreetMap puts on a road were moved there, San Francisco and Anchorage among them. Most of the rest are Alaskan villages with no road at all.

Three more rows in that file were set by hand. Liberty and Newburg in Pennsylvania and Wilmington in Illinois each share their name with another town in the same state, and the highway exit in the station's address shows which one is meant.

### Answering a request

1. **Resolve the places.** `City, ST` comes from the local `Place` table, coordinates are read directly, and anything else goes to the geocoder.
2. **Get the route.** This is a single OpenRouteService call using the truck (`driving-hgv`) profile. It requests the compact encoded-polyline format, which is about six times smaller than GeoJSON. Routes are cached for 24 hours.
3. **Find stations near the route.** The route is resampled to a point every half mile, each point knowing its mile marker. A SciPy KD-tree, built on 3-D unit vectors so distances stay correct across the country, finds every station within 8 miles of the route in a few milliseconds.
4. **Choose the stops.** See the next section.
5. **Respond** with the stops, totals, route and map link.

### Choosing the stops

The cheapest possible plan is easy to compute with the classic greedy rule:

- if a cheaper station is within reach, buy just enough to get there;
- otherwise, fill up.

On real data, though, that rule stops far too often: 20 times between Seattle and Miami, five of them for less than three gallons. So the planner works in two passes:

1. **Pick the stops** with a shortest-path search (dynamic programming) over the stations, sorted by mile marker. Moving from one station to another within 500 miles costs the fuel for that leg plus a $5 penalty per stop. A stop is only added if it saves more than $5.
2. **Decide the gallons** at those stops with the greedy rule, so cheap fuel is carried past expensive stations.

On the eight long routes I measured, this made 2 to 8 stops where the greedy rule made 4 to 20, and the fuel cost 0.6% to 1.9% more than the theoretical minimum. New York to Los Angeles takes 6 stops instead of 11. If the price list has no station for a stretch longer than the tank range, the API says exactly where.

### Speed

Measured from a home connection:

| | Time |
|---|---|
| New trip, New York to Los Angeles | about 1.5 s, of which about 1.2 s is waiting for OpenRouteService |
| Same trip again | 40 to 70 ms, with no API call |
| Our own work: stations, optimizer, JSON | 15 to 40 ms |

The station list is loaded into memory once per process, so requests never query the stations table. Restart the server after importing stations again.

## Assumptions

- The vehicle has a 500-mile range (a 50-gallon tank) and does 10 miles per gallon.
- The truck leaves with just enough fuel to reach its first stop. That fuel is reported as `starting_fuel_gallons` and priced at the first stop, so `total_gallons` always equals the distance divided by 10.
- The first stop is the best station within 25 miles of the first one on the route.
- A station counts as on the route if it is within 8 miles of it. Station locations are town-level, because the price file only has a city and state.
- The $5 stop penalty only affects which stops are chosen. Reported costs are fuel only.
- Routes avoid border crossings, so a trip never leaves the US.
- The price list is thin in places. It has no stations in Alaska or Hawaii and only 8 in California, all near the Mexican border. A trip that needs fuel where the list has none, such as Los Angeles to San Francisco, gets a 422 that says where the gap is.

These values live in `config/settings.py`: `VEHICLE_RANGE_MILES`, `VEHICLE_MILES_PER_GALLON`, `MAX_MILES_OFF_ROUTE`, `FIRST_STOP_WITHIN_MILES` and `STOP_PENALTY_DOLLARS`.

## Tests

```bash
python manage.py test
```

52 tests cover:

- name matching, the import commands and the town lookup;
- the geometry helpers and the polyline decoder;
- the station search and the optimizer, including a check that a random plan never runs dry or overfills the tank;
- the OpenRouteService client and the API endpoints.

All network calls are faked, so the tests run offline in under a second.

## Postman

Import `postman/fuel-route-planner.postman_collection.json`. It has example trips, the different input formats and three error cases. Successful plans draw the route and stops in Postman's Visualize tab.

## Project layout

```
config/          settings and root URLs
stations/        FuelStation and Place models, data import commands
planner/
  locations.py   turns text into coordinates
  openroute.py   OpenRouteService client with caching
  corridor.py    finds stations along the route
  optimizer.py   chooses stops and gallons
  services.py    puts a plan together
  views.py       JSON endpoint and map page
data/            fuel prices, Census places, extra towns
postman/         Postman collection
```

## Data sources

- `fuel-prices-for-be-assessment.csv`: the provided truck stop price list.
- [2025 US Census Gazetteer](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html), national places file (public domain).
- `extra_places.csv`: town coordinates from [OpenStreetMap](https://www.openstreetmap.org/copyright) via Nominatim, © OpenStreetMap contributors (ODbL).
- Routing and geocoding by [openrouteservice](https://openrouteservice.org) (HeiGIT).
- Maps drawn with [Leaflet](https://leafletjs.com) on OpenStreetMap tiles.

## What I would add next

- **Exit-level station locations.** The addresses name the interstate and exit (`I-44, EXIT 283`), so matching them to OpenStreetMap motorway junctions would place each station exactly instead of at the town centre.
- **Detours in the cost.** Count the extra driving to stations that sit off the route.
- **Request options** for the tank range, the mpg and the current fuel level.
- **A shared cache** in Redis instead of per-process memory, plus rate limiting for clients.
- **PostGIS** for spatial queries if the station list grows far beyond a few thousand.
