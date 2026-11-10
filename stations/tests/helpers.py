from stations.models import FuelStation, Place
from stations.places import place_key


def add_place(name, state, latitude, longitude):
    return Place.objects.create(
        name=name,
        state=state,
        lookup_key=place_key(name),
        latitude=latitude,
        longitude=longitude,
    )


def add_station(opis_id, price, latitude, longitude, name=None):
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=name or f"STATION {opis_id}",
        address="I-70",
        city="Testville",
        state="KS",
        rack_id=1,
        price=price,
        latitude=latitude,
        longitude=longitude,
    )
