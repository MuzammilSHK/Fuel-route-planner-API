import csv
import io
import re
import unicodedata
import zipfile

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

ABBREVIATIONS = {
    "st": "saint",
    "ste": "sainte",
    "ft": "fort",
    "mt": "mount",
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
}

CONSOLIDATED_CITY = re.compile(r"\(balance\)|government|urban county|/")


def place_key(name):
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", plain.lower().replace("'", ""))
    return "".join(ABBREVIATIONS.get(word, word) for word in words)


def clean_census_name(raw_name):
    words = raw_name.replace("(balance)", "").split()
    while len(words) > 1 and (words[-1].islower() or words[-1] == "CDP"):
        words.pop()
    return " ".join(words)


def census_aliases(raw_name, name):
    if name.endswith(" City"):
        yield name.removesuffix(" City")
    for prefix in ("Town of ", "City of ", "Village of "):
        if name.startswith(prefix):
            yield name.removeprefix(prefix)
    if CONSOLIDATED_CITY.search(raw_name):
        yield re.split(r"[-/,]", name)[0].strip()


def read_census_places(path):
    with zipfile.ZipFile(path) as archive:
        text = archive.read(archive.namelist()[0]).decode("utf-8")
    for row in csv.DictReader(io.StringIO(text), delimiter="|"):
        if row["USPS"] in STATE_NAMES:
            yield row


def incorporated_first(rows):
    return sorted(rows, key=lambda row: row["NAME"].endswith(" CDP"))


def read_extra_places(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))
