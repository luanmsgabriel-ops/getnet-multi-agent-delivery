"""Compatible ASGI entrypoint; import app.http_factory for reusable factories."""
from app.http_factory import *  # Preserve existing public imports.

app = create_app()
