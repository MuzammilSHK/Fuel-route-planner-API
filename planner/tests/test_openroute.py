from unittest import mock

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from planner import openroute
from planner.exceptions import RouteNotFound, RoutingUnavailable
from planner.locations import Location

START = Location("Start", 38.5, -120.2, "coordinates")
FINISH = Location("Finish", 40.7, -120.95, "coordinates")
ROUTE_REPLY = {
    "routes": [
        {
            "summary": {"distance": 151.2, "duration": 9000},
            "geometry": "_p~iF~ps|U_ulLnnqC",
        }
    ]
}


def reply(status, payload):
    return mock.Mock(
        status_code=status, ok=status < 400, json=mock.Mock(return_value=payload)
    )


@override_settings(ORS_API_KEY="test-key")
class OpenRouteTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch.object(openroute.session, "request")
        self.request = patcher.start()
        self.addCleanup(patcher.stop)

    def test_decodes_the_route_and_serves_repeats_from_the_cache(self):
        self.request.return_value = reply(200, ROUTE_REPLY)
        route, cached = openroute.get_route(START, FINISH)
        self.assertFalse(cached)
        self.assertEqual(route.coordinates, [[-120.2, 38.5], [-120.95, 40.7]])
        self.assertEqual((route.miles, route.seconds), (151.2, 9000))

        again, cached = openroute.get_route(START, FINISH)
        self.assertTrue(cached)
        self.assertEqual(again, route)
        self.assertEqual(self.request.call_count, 1)

    def test_sends_the_key_and_keeps_the_route_inside_the_usa(self):
        self.request.return_value = reply(200, ROUTE_REPLY)
        openroute.get_route(START, FINISH)
        method, url = self.request.call_args.args
        options = self.request.call_args.kwargs
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith(f"/directions/{settings.ORS_PROFILE}/json"))
        self.assertEqual(options["headers"], {"Authorization": "test-key"})
        self.assertEqual(options["json"]["options"], {"avoid_borders": "all"})
        self.assertEqual(
            options["json"]["coordinates"], [[-120.2, 38.5], [-120.95, 40.7]]
        )

    def test_unroutable_points_become_a_422_with_the_services_message(self):
        message = "Could not find routable point within a radius of 5000.0 meters"
        self.request.return_value = reply(
            404, {"error": {"code": 2010, "message": message}}
        )
        with self.assertRaisesMessage(RouteNotFound, message):
            openroute.get_route(START, FINISH)

    def test_rejected_keys_quota_and_outages_become_a_503(self):
        for status in (401, 403, 429, 502):
            self.request.return_value = reply(status, {"error": "unavailable"})
            with self.assertRaises(RoutingUnavailable):
                openroute.get_route(START, FINISH)

    def test_timeouts_become_a_503(self):
        self.request.side_effect = requests.Timeout()
        with self.assertRaises(RoutingUnavailable):
            openroute.get_route(START, FINISH)

    @override_settings(ORS_API_KEY="")
    def test_missing_key_is_reported_without_calling_the_api(self):
        with self.assertRaisesMessage(RoutingUnavailable, ".env"):
            openroute.get_route(START, FINISH)
        self.request.assert_not_called()

    def test_geocoder_returns_the_best_specific_place(self):
        feature = {
            "geometry": {"coordinates": [-77.0365, 38.8977]},
            "properties": {"label": "White House, Washington, DC, USA"},
        }
        self.request.return_value = reply(200, {"features": [feature]})
        result, cached = openroute.geocode("1600 Pennsylvania Ave NW")
        self.assertFalse(cached)
        layers = self.request.call_args.kwargs["params"]["layers"]
        self.assertIn("address", layers)
        self.assertNotIn("region", layers)
        self.assertEqual(
            result,
            {
                "label": "White House, Washington, DC, USA",
                "latitude": 38.8977,
                "longitude": -77.0365,
            },
        )

    def test_geocoder_remembers_places_it_could_not_find(self):
        self.request.return_value = reply(200, {"features": []})
        self.assertEqual(openroute.geocode("Atlantis"), (None, False))
        self.assertEqual(openroute.geocode("Atlantis"), (None, True))
        self.assertEqual(self.request.call_count, 1)
