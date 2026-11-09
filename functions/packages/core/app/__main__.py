"""DigitalOcean Functions entry point. The API itself is the vendored `app` package."""

from app.serverless import main

__all__ = ["main"]
