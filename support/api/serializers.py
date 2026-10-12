from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    content = serializers.CharField(
        max_length=1000,
        allow_blank=False,
        trim_whitespace=True,
    )