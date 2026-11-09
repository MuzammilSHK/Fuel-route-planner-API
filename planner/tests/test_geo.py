from django.test import SimpleTestCase

from planner.geo import chord_to_miles, decode_polyline, haversine_miles, miles_to_chord


class GeoTests(SimpleTestCase):
    def test_haversine_matches_the_known_new_york_to_los_angeles_distance(self):
        miles = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(float(miles), 2445, delta=5)

    def test_chord_conversion_round_trips(self):
        for miles in (0.5, 8, 250):
            self.assertAlmostEqual(float(chord_to_miles(miles_to_chord(miles))), miles)

    def test_decodes_googles_reference_polyline(self):
        self.assertEqual(
            decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@"),
            [[-120.2, 38.5], [-120.95, 40.7], [-126.453, 43.252]],
        )
