import numpy as np

EARTH_RADIUS_MILES = 3958.8


def unit_vectors(latitudes, longitudes):
    lat = np.radians(latitudes)
    lon = np.radians(longitudes)
    return np.column_stack(
        (np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat))
    )


def haversine_miles(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def miles_to_chord(miles):
    return 2 * np.sin(miles / (2 * EARTH_RADIUS_MILES))


def chord_to_miles(chord):
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.clip(chord / 2, 0, 1))


def decode_polyline(encoded):
    numbers = []
    value = shift = 0
    for character in encoded:
        chunk = ord(character) - 63
        value |= (chunk & 0x1F) << shift
        shift += 5
        if chunk < 0x20:
            numbers.append(~(value >> 1) if value & 1 else value >> 1)
            value = shift = 0
    latitudes = np.cumsum(numbers[0::2]) / 1e5
    longitudes = np.cumsum(numbers[1::2]) / 1e5
    return np.column_stack((longitudes, latitudes)).tolist()
