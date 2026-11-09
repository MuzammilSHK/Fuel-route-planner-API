from django.db import models


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=6, decimal_places=3)
    latitude = models.FloatField()
    longitude = models.FloatField()

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state}"


class Place(models.Model):
    name = models.CharField(max_length=120)
    state = models.CharField(max_length=2)
    lookup_key = models.CharField(max_length=120)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["state", "lookup_key"], name="unique_place_lookup"
            ),
        ]

    def __str__(self):
        return f"{self.name}, {self.state}"
