from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)

    def validate(self, attrs):
        if attrs["start"].lower() == attrs["finish"].lower():
            raise serializers.ValidationError(
                {"finish": "Start and finish must be different."}
            )
        return attrs
