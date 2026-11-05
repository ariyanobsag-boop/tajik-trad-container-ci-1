"""
TAJIK_TRAD - Isolated Public Read-Only Reference Feed.

Only these routes are exposed:
    GET /health
    GET /api/v1/feed/spot
    GET /api/v1/feed/intraday

This application intentionally excludes:
    - Historical market API routes.
    - Signals and alerts.
    - Provider validation endpoints.
    - Trading or execution routes.

The feed contains indicative reference data for educational display.
It is not a trading or execution service.
"""

from fastapi import FastAPI
from xaus_readonly_api import register_xaus_readonly_routes


app = FastAPI(
    title="TAJIK_TRAD Read-Only Reference Feed",
    version="1.0.0",
    description="Limited educational reference-data service.",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# Register only the two read-only reference-data routes.
register_xaus_readonly_routes(app)


@app.get(
    "/health",
    include_in_schema=False,
    name="public_feed_health",
)
def public_feed_health():
    return {
        "status": "online",
        "service": "read-only-reference-feed",
    }


@app.middleware("http")
async def add_security_headers(request, call_next):

    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response
