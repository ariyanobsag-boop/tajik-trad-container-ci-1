"""
TAJIK_TRAD - XAUS Read-Only API Routes

Registers two independent FastAPI endpoints:

    GET /api/v1/feed/spot
    GET /api/v1/feed/intraday

This module is strictly read-only.

It does not:
    - Modify historical CSV data.
    - Modify market snapshots.
    - Generate OHLC candles from sampled points.
    - Create trading signals or alerts.
    - Execute or manage transactions.
    - Store API keys or credentials.

Reference prices are indicative data, not guaranteed or tradable quotes.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import HTTPException, Query, Response

import xaus_readonly_feed as feed


# ---------------------------------------------------------------------------
# Server-side cache policy
# ---------------------------------------------------------------------------

SPOT_CACHE_TTL_SECONDS = 65.0
INTRADAY_CACHE_TTL_SECONDS = 305.0

SPOT_MAX_AGE_SECONDS = 180
INTRADAY_MAX_AGE_SECONDS = 600


# ---------------------------------------------------------------------------
# Cache state
# ---------------------------------------------------------------------------

_CACHE: dict[str, dict[str, Any]] = {}

_LOCKS: dict[str, Lock] = {}

_LOCKS_GUARD = Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _get_lock(key: str) -> Lock:
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = Lock()

        return _LOCKS[key]


def clear_readonly_cache() -> None:
    """
    Clear in-process cache.

    Intended for isolated tests and controlled maintenance.
    """

    with _LOCKS_GUARD:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Response freshness
# ---------------------------------------------------------------------------

def _decorate_payload(
    payload: dict[str, Any],
    entry: dict[str, Any],
    cache_status: str,
    cache_ttl: float,
    timestamp_field: str,
    maximum_age: int,
    cache_key: str,
) -> dict[str, Any]:

    result = deepcopy(payload)

    now = _utc_now()
    now_monotonic = monotonic()

    source_time = feed._parse_timestamp(
        result.get(timestamp_field)
    )

    source_age = feed._age_seconds(
        source_time,
        now,
    )

    provider_status = str(
        result.get("provider_status", "unknown")
    ).lower()

    if cache_key.startswith("intraday:") and not result.get("points"):
        freshness = "unavailable"

    else:
        freshness = feed._freshness_status(
            provider_status=provider_status,
            age_seconds=source_age,
            max_age_seconds=maximum_age,
            explicit_stale=(
                result.get("stale_flag") is True
            ),
        )

    result["source_age_seconds"] = (
        round(max(0.0, source_age), 2)
        if source_age is not None
        else None
    )

    result["freshness_status"] = freshness

    result["served_at"] = _iso_utc(now)

    result["provider_received_at"] = (
        entry.get("provider_received_at")
    )

    result["server_cache_status"] = cache_status

    result["server_cache_age_seconds"] = round(
        max(
            0.0,
            now_monotonic - entry["stored_monotonic"],
        ),
        2,
    )

    result["server_cache_ttl_seconds"] = cache_ttl

    return result


# ---------------------------------------------------------------------------
# Shared cached fetch function
# ---------------------------------------------------------------------------

def _cached_fetch(
    cache_key: str,
    fetcher,
    cache_ttl: float,
    timestamp_field: str,
    maximum_age: int,
) -> dict[str, Any]:

    key_lock = _get_lock(cache_key)

    with key_lock:

        now_monotonic = monotonic()

        entry = _CACHE.get(cache_key)

        if (
            entry is not None
            and now_monotonic - entry["stored_monotonic"] < cache_ttl
        ):

            cache_status = "hit"

        else:

            try:
                provider_payload = fetcher()

            except feed.FeedRequestError as exc:

                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "upstream_unavailable",
                        "error_type": type(exc).__name__,
                        "message": (
                            "Reference data is temporarily unavailable."
                        ),
                    },
                ) from exc

            except feed.FeedDataError as exc:

                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "invalid_provider_data",
                        "error_type": type(exc).__name__,
                        "message": (
                            "The provider returned unusable data."
                        ),
                    },
                ) from exc

            except Exception as exc:

                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "feed_processing_failed",
                        "error_type": type(exc).__name__,
                    },
                ) from exc

            if not isinstance(provider_payload, dict):
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "invalid_normalized_payload"
                    },
                )

            entry = {
                "payload": deepcopy(provider_payload),
                "stored_monotonic": monotonic(),
                "provider_received_at": provider_payload.get(
                    "received_at"
                ),
            }

            _CACHE[cache_key] = entry

            cache_status = "miss"

        return _decorate_payload(
            payload=entry["payload"],
            entry=entry,
            cache_status=cache_status,
            cache_ttl=cache_ttl,
            timestamp_field=timestamp_field,
            maximum_age=maximum_age,
            cache_key=cache_key,
        )


# ---------------------------------------------------------------------------
# FastAPI route registration
# ---------------------------------------------------------------------------

def register_xaus_readonly_routes(app):

    if app is None or not hasattr(app, "add_api_route"):
        raise RuntimeError("A valid FastAPI application is required.")

    spot_path = "/api/v1/feed/spot"
    intraday_path = "/api/v1/feed/intraday"

    existing_paths = {
        getattr(route, "path", None)
        for route in app.routes
    }

    conflicts = {
        spot_path,
        intraday_path,
    }.intersection(existing_paths)

    if conflicts:
        raise RuntimeError(
            "Feed route conflict: " + ", ".join(sorted(conflicts))
        )

    # -----------------------------------------------------------------------
    # Spot endpoint
    # -----------------------------------------------------------------------

    def feed_spot(response: Response):

        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"

        return _cached_fetch(
            cache_key="spot",
            fetcher=feed.fetch_spot,
            cache_ttl=SPOT_CACHE_TTL_SECONDS,
            timestamp_field="source_timestamp",
            maximum_age=SPOT_MAX_AGE_SECONDS,
        )

    # -----------------------------------------------------------------------
    # Intraday endpoint
    # -----------------------------------------------------------------------

    def feed_intraday(
        response: Response,
        hours: int = Query(default=6, ge=1, le=48),
    ):

        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"

        cache_key = f"intraday:{hours}"

        return _cached_fetch(
            cache_key=cache_key,
            fetcher=lambda: feed.fetch_intraday(hours=hours),
            cache_ttl=INTRADAY_CACHE_TTL_SECONDS,
            timestamp_field="latest_source_timestamp",
            maximum_age=INTRADAY_MAX_AGE_SECONDS,
        )

    # -----------------------------------------------------------------------
    # Register only GET routes
    # -----------------------------------------------------------------------

    app.add_api_route(
        spot_path,
        feed_spot,
        methods=["GET"],
        name="xaus_readonly_spot",
        tags=["Read-Only Reference Data"],
        response_model=None,
        description=(
            "Indicative XAU/USD spot reference data with "
            "source timestamp and freshness metadata."
        ),
    )

    app.add_api_route(
        intraday_path,
        feed_intraday,
        methods=["GET"],
        name="xaus_readonly_intraday",
        tags=["Read-Only Reference Data"],
        response_model=None,
        description=(
            "Sampled XAU/USD reference price points for line-chart "
            "display. Not OHLC candles."
        ),
    )

    return {
        "spot": feed_spot,
        "intraday": feed_intraday,
    }
