import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

application = get_asgi_application()

# 🚀 Required for Vercel: expose handler named "app"
app = application
