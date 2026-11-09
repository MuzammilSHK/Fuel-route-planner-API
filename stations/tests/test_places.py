from django.test import SimpleTestCase

from stations.places import census_aliases, clean_census_name, place_key


class PlaceKeyTests(SimpleTestCase):
    def test_spellings_of_the_same_town_share_a_key(self):
        self.assertEqual(place_key("St. Louis"), place_key("Saint Louis"))
        self.assertEqual(place_key("ST LOUIS"), "saintlouis")
        self.assertEqual(place_key("Ft Worth"), place_key("Fort Worth"))
        self.assertEqual(place_key("N Little Rock"), "northlittlerock")
        self.assertEqual(place_key("Smith's Creek"), place_key("Smiths Creek"))
        self.assertEqual(place_key("Española"), "espanola")

    def test_spaces_and_punctuation_do_not_matter(self):
        self.assertEqual(place_key("Mc Lean"), place_key("McLean"))
        self.assertEqual(place_key("  New   Castle "), "newcastle")


class CensusNameTests(SimpleTestCase):
    def test_strips_the_legal_description(self):
        self.assertEqual(clean_census_name("Big Cabin town"), "Big Cabin")
        self.assertEqual(clean_census_name("Ellenton CDP"), "Ellenton")
        self.assertEqual(
            clean_census_name("Indianapolis city (balance)"), "Indianapolis"
        )
        self.assertEqual(clean_census_name("Oklahoma City city"), "Oklahoma City")

    def test_offers_the_names_people_actually_use(self):
        self.assertEqual(
            list(census_aliases("Boise City city", "Boise City")), ["Boise"]
        )
        self.assertEqual(
            list(census_aliases("Town of Pecos city", "Town of Pecos")), ["Pecos"]
        )
        raw = "Nashville-Davidson metropolitan government (balance)"
        self.assertEqual(
            list(census_aliases(raw, clean_census_name(raw))), ["Nashville"]
        )

    def test_leaves_ordinary_hyphenated_names_alone(self):
        self.assertEqual(
            list(census_aliases("Winston-Salem city", "Winston-Salem")), []
        )
