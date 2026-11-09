from django.shortcuts import render
from django.urls import reverse
from django.utils.http import urlencode
from django.views import View
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import RouteRequestSerializer
from .services import plan_trip

MAP_TEMPLATE = "planner/route_map.html"


class RoutePlanView(APIView):
    def get(self, request):
        serializer = RouteRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        plan = plan_trip(**serializer.validated_data)
        map_url = request.build_absolute_uri(
            f"{reverse('route-map')}?{urlencode(serializer.validated_data)}"
        )
        return Response({"map_url": map_url, **plan})


class RouteMapView(View):
    def get(self, request):
        serializer = RouteRequestSerializer(data=request.GET)
        if not serializer.is_valid():
            problems = " ".join(
                f"{field}: {messages[0]}"
                for field, messages in serializer.errors.items()
            )
            return render(request, MAP_TEMPLATE, {"error": problems}, status=400)
        try:
            plan = plan_trip(**serializer.validated_data)
        except APIException as error:
            context = {"error": error.detail}
            return render(request, MAP_TEMPLATE, context, status=error.status_code)
        return render(request, MAP_TEMPLATE, {"plan": plan})
