from rest_framework import status
from rest_framework.exceptions import APIException


class LocationNotFound(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "That location could not be found in the USA."


class RouteNotFound(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "No drivable route was found between these locations."


class FuelGap(APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Part of this route is out of range of every fuel station."


class RoutingUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The routing service is unavailable, please try again shortly."


class StationsNotLoaded(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = (
        "No fuel stations are loaded yet, run import_places and import_stations."
    )
