"""Compatible ASGI entrypoint; import app.context_factory for reusable factories."""
from app.context_factory import *  # Preserve existing public imports.

app = create_app()
