from django.urls import re_path

from picaterpillar import settings
from restapi import consumers

websocket_urlpatterns = [
    re_path(r'ws/robot/$', consumers.RobotConsumer.as_asgi()),
]
if settings.DEBUG:
    websocket_urlpatterns.append(re_path(r'ws/uart/$', consumers.UartConsumer.as_asgi()))