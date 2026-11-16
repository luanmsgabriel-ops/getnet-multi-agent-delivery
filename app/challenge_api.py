"""Compatible ASGI entrypoint; import app.challenge_factory for reusable factories."""
from app.challenge_factory import *  # Preserve existing public imports.

app = create_app()
