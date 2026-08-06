import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

# get_asgi_application() must run BEFORE any module that imports Django
# models (e.g. research.consumers imports django.contrib.auth.models).
# Calling it first populates Django's app registry so those imports succeed.
from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from research import consumers

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter([
            path('ws/notifications/', consumers.NotificationConsumer.as_asgi()),
        ])
    ),
})