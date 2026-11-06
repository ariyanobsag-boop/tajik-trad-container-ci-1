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

import logging
import math

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import HTTPException, Query, Response

import xaus_readonly_feed as feed


logger = logging.getLogger(__name__)


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

# Incremented on every clear so in-flight fetches cannot repopulate the cache.
_CACHE_GENERATION = 0


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
    Clear in-process cache and invalidate all fetches already in progress.

    Intended for isolated tests and controlled maintenance.
    """
    global _CACHE_GENERATION

    with _LOCKS_GUARD:
        _CACHE_GENERATION += 1
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Normalized payload validation
# ---------------------------------------------------------------------------

def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False

    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _is_positive_number(value: Any) -> bool:
    return _is_finite_number(value) and float(value) > 0


def _is_optional_nonnegative_number(value: Any) -> bool:
    return (
        value is None
        or (
            _is_finite_number(value)
            and float(value) >= 0
        )
    )


def _is_count(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_timestamp(value: Any, allow_none: bool = False) -> bool:
    if value is None:
        return allow_none

    if not isinstance(value, str):
        return False

    try:
        return feed._parse_timestamp(value) is not None
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_common_metadata(payload: dict[str, Any]) -> bool:
    return (
        payload.get("provider") == "xaus.com"
        and payload.get("instrument") == "XAU/USD"
        and isinstance(payload.get("provider_status"), str)
        and bool(payload["provider_status"].strip())
        and isinstance(payload.get("provider_source"), (str, type(None)))
        and _is_timestamp(payload.get("received_at"))
        and _is_optional_nonnegative_number(
            payload.get("source_age_seconds")
        )
        and payload.get("freshness_status")
        in {"fresh", "stale", "unavailable"}
        and isinstance(payload.get("notice"), str)
        and bool(payload["notice"].strip())
    )


def _validate_spot_payload(payload: dict[str, Any]) -> bool:
    required = {
        "provider",
        "instrument",
        "data_type",
        "price_usd_per_troy_ounce",
        "source_timestamp",
        "received_at",
        "source_age_seconds",
        "provider_status",
        "provider_source",
        "freshness_status",
        "stale_flag",
        "chart_type",
        "notice",
    }

    if not required.issubset(payload):
        return False

    return (
        _valid_common_metadata(payload)
        and payload.get("data_type") == "spot_reference"
        and _is_positive_number(
            payload.get("price_usd_per_troy_ounce")
        )
        and _is_timestamp(
            payload.get("source_timestamp"),
            allow_none=True,
        )
        and isinstance(payload.get("stale_flag"), bool)
        and payload.get("chart_type") == "single_reference_value"
    )


def _validate_intraday_payload(payload: dict[str, Any]) -> bool:
    required = {
        "provider",
        "instrument",
        "data_type",
        "chart_type",
        "points",
        "point_count",
        "source_point_count",
        "invalid_point_count",
        "duplicate_point_count",
        "future_point_count",
        "source_order_valid",
        "quality_warnings",
        "source_coverage_seconds",
        "actual_coverage_seconds",
        "latest_source_timestamp",
        "received_at",
        "source_age_seconds",
        "provider_status",
        "provider_source",
        "freshness_status",
        "notice",
    }

    if not required.issubset(payload):
        return False

    if not _valid_common_metadata(payload):
        return False

    if (
        payload.get("data_type") != "sampled_spot_price_points"
        or payload.get("chart_type") != "line"
    ):
        return False

    points = payload.get("points")
    if not isinstance(points, list):
        return False

    if len(points) > feed.MAX_INTRADAY_POINTS:
        return False

    point_count = payload.get("point_count")
    source_count = payload.get("source_point_count")
    invalid_count = payload.get("invalid_point_count")
    duplicate_count = payload.get("duplicate_point_count")
    future_count = payload.get("future_point_count")

    counts = (
        point_count,
        source_count,
        invalid_count,
        duplicate_count,
        future_count,
    )

    if not all(_is_count(value) for value in counts):
        return False

    if (
        point_count != len(points)
        or point_count > feed.MAX_INTRADAY_POINTS
        or source_count > feed.MAX_INTRADAY_POINTS
    ):
        return False

    # Every source point must be accounted for exactly once.
    if source_count != (
        point_count + invalid_count + duplicate_count + future_count
    ):
        return False

    if not isinstance(payload.get("source_order_valid"), bool):
        return False

    warnings = payload.get("quality_warnings")
    if not isinstance(warnings, list):
        return False

    if not all(isinstance(item, str) for item in warnings):
        return False

    expected_warnings = set()

    if invalid_count:
        expected_warnings.add("invalid_points_removed")
    if duplicate_count:
        expected_warnings.add("duplicate_timestamps_removed")
    if future_count:
        expected_warnings.add("future_points_removed")
    if not payload["source_order_valid"]:
        expected_warnings.add("source_order_was_not_chronological")

    if set(warnings) != expected_warnings or len(warnings) != len(expected_warnings):
        return False

    if not _is_optional_nonnegative_number(
        payload.get("source_coverage_seconds")
    ):
        return False

    if not _is_optional_nonnegative_number(
        payload.get("actual_coverage_seconds")
    ):
        return False

    if not _is_timestamp(
        payload.get("latest_source_timestamp"),
        allow_none=(point_count == 0),
    ):
        return False

    previous_timestamp = None
    seen_timestamps = set()
    parsed_points = []

    for point in points:
        if not isinstance(point, dict):
            return False

        epoch_seconds = point.get("epoch_seconds")
        timestamp_text = point.get("t")
        price = point.get("p")

        if (
            not isinstance(epoch_seconds, int)
            or isinstance(epoch_seconds, bool)
            or not _is_timestamp(timestamp_text)
            or not _is_positive_number(price)
        ):
            return False

        try:
            parsed_time = feed._parse_timestamp(timestamp_text)
            epoch = parsed_time.timestamp()
        except (TypeError, ValueError, OverflowError, AttributeError):
            return False

        if int(epoch) != epoch_seconds:
            return False

        timestamp_key = round(epoch, 3)

        if timestamp_key in seen_timestamps:
            return False

        if (
            previous_timestamp is not None
            and parsed_time < previous_timestamp
        ):
            return False

        seen_timestamps.add(timestamp_key)
        previous_timestamp = parsed_time
        parsed_points.append(parsed_time)

    if point_count:
        latest = feed._parse_timestamp(
            payload["latest_source_timestamp"]
        )

        if latest != parsed_points[-1]:
            return False

        if point_count >= 2:
            expected_coverage = round(
                (
                    parsed_points[-1] - parsed_points[0]
                ).total_seconds(),
                2,
            )
            actual_coverage = payload.get("actual_coverage_seconds")

            if (
                not _is_finite_number(actual_coverage)
                or abs(float(actual_coverage) - expected_coverage) > 0.011
            ):
                return False
        elif payload.get("actual_coverage_seconds") is not None:
            return False

    else:
        if payload.get("actual_coverage_seconds") is not None:
            return False

        if payload.get("freshness_status") != "unavailable":
            return False

    return True


def _validate_normalized_payload(
    cache_key: str,
    payload: Any,
) -> bool:
    if not isinstance(payload, dict):
        return False

    data_type = payload.get("data_type")

    if cache_key == "spot" or cache_key.startswith("spot:"):
        return _validate_spot_payload(payload)

    if cache_key.startswith("intraday:"):
        return _validate_intraday_payload(payload)

    if data_type == "spot_reference":
        return _validate_spot_payload(payload)

    if data_type == "sampled_spot_price_points":
        return _validate_intraday_payload(payload)

    # Compatibility for the existing generic cache helper tests.
    # Production routes always use the strict Spot or Intraday schemas above.
    legacy_price = payload.get(
        "price_usd_per_troy_ounce",
        payload.get("price"),
    )

    return (
        _is_positive_number(legacy_price)
        and _is_timestamp(payload.get("source_timestamp"))
        and _is_timestamp(payload.get("received_at"))
        and isinstance(payload.get("provider_status"), str)
        and bool(payload["provider_status"].strip())
    )


def _is_intraday_payload(
    cache_key: str,
    payload: dict[str, Any],
) -> bool:
    return (
        cache_key.startswith("intraday:")
        or payload.get("data_type") == "sampled_spot_price_points"
    )


def _should_bypass_cache(
    cache_key: str,
    payload: dict[str, Any],
) -> bool:
    provider_status = str(
        payload.get("provider_status", "")
    ).lower()

    freshness_status = str(
        payload.get("freshness_status", "")
    ).lower()

    if (
        provider_status == "unavailable"
        or freshness_status == "unavailable"
    ):
        return True

    if _is_intraday_payload(cache_key, payload):
        return not payload.get("points")

    return False


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

    if (
        provider_status == "unavailable"
        or result.get("freshness_status") == "unavailable"
        or (
            _is_intraday_payload(cache_key, result)
            and not result.get("points")
        )
    ):
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

        with _LOCKS_GUARD:
            generation = _CACHE_GENERATION
            entry = _CACHE.get(cache_key)

            if (
                entry is not None
                and now_monotonic - entry["stored_monotonic"] < cache_ttl
            ):
                cache_status = "hit"

            else:
                if entry is not None:
                    _CACHE.pop(cache_key, None)

                entry = None
                cache_status = None

        if entry is None:

            try:
                provider_payload = fetcher()

            except feed.FeedRequestError as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "upstream_unavailable",
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
                        "message": (
                            "The provider returned unusable data."
                        ),
                    },
                ) from exc

            except Exception as exc:
                logger.exception(
                    "Unexpected error while processing reference data."
                )

                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "feed_processing_failed",
                        "message": (
                            "Reference data could not be processed."
                        ),
                    },
                ) from exc

            if not _validate_normalized_payload(
                cache_key,
                provider_payload,
            ):
                raise HTTPException(
                    status_code=502,
                    detail={
                        "error": "invalid_normalized_payload",
                        "message": (
                            "The normalized reference data failed validation."
                        ),
                    },
                )

            entry = {
                "payload": deepcopy(provider_payload),
                "stored_monotonic": monotonic(),
                "provider_received_at": provider_payload.get(
                    "received_at"
                ),
            }

            if _should_bypass_cache(cache_key, provider_payload):
                cache_status = "bypass"

            else:
                with _LOCKS_GUARD:
                    if generation != _CACHE_GENERATION:
                        # A clear operation happened during this fetch.
                        cache_status = "bypass"
                    else:
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
