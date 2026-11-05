"""
TAJIK_TRAD - XAUS Read-Only Feed

Purpose:
    Fetch and validate public reference data for educational display.

Endpoints:
    /api/v1/spot
    /api/v1/intraday

Important:
    - Read-only HTTP GET requests only.
    - No trading, execution, strategy, signals, or alerts.
    - Spot price and sampled intraday points remain separate.
    - Intraday points are for a line chart only.
    - No fabricated OHLC candles.
    - No CSV or snapshot writes.
    - No API key is required or stored.

All prices are indicative reference data, not guaranteed or tradable quotes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import math
import requests


API_BASE = "https://xaus.com/api/v1"

SPOT_URL = API_BASE + "/spot"
INTRADAY_URL = API_BASE + "/intraday"

SPOT_MAX_AGE_SECONDS = 180
INTRADAY_MAX_AGE_SECONDS = 600

REQUEST_TIMEOUT = (5, 12)

USER_AGENT = "TAJIK_TRAD-ReadOnly-Educational-Feed/1.0"


class FeedError(RuntimeError):
    """Base error for read-only feed operations."""


class FeedRequestError(FeedError):
    """HTTP, transport, or JSON response error."""


class FeedDataError(FeedError):
    """Invalid or unusable source data."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime | None:
    """
    Parse ISO-8601 timestamps or Unix timestamps.

    Numeric Unix values:
        seconds are accepted;
        milliseconds are accepted when the value is large enough.
    """

    if value is None or isinstance(value, bool):
        return None

    try:
        if isinstance(value, (int, float)):
            number = float(value)

            if not math.isfinite(number):
                return None

            if abs(number) >= 1_000_000_000_000:
                number /= 1000.0

            return datetime.fromtimestamp(number, tz=timezone.utc)

        text = str(value).strip()

        if not text:
            return None

        # Numeric timestamps supplied as strings.
        try:
            number = float(text)

            if math.isfinite(number):
                if abs(number) >= 1_000_000_000_000:
                    number /= 1000.0

                return datetime.fromtimestamp(number, tz=timezone.utc)

        except ValueError:
            pass

        # ISO-8601 timestamps.
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _positive_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)

        if not math.isfinite(number) or number <= 0:
            return None

        return number

    except (ValueError, TypeError, OverflowError):
        return None


def _age_seconds(
    source_time: datetime | None,
    received_time: datetime,
) -> float | None:

    if source_time is None:
        return None

    return (received_time - source_time).total_seconds()


def _freshness_status(
    provider_status: str,
    age_seconds: float | None,
    max_age_seconds: int,
    explicit_stale: bool = False,
) -> str:

    status = str(provider_status or "unknown").strip().lower()

    if status == "unavailable":
        return "unavailable"

    if explicit_stale or status == "stale":
        return "stale"

    # Unknown provider state is not enough evidence to claim freshness.
    if status != "fresh":
        return "stale"

    if age_seconds is None:
        return "stale"

    # Allow a small clock-skew margin only.
    if age_seconds < -30:
        return "stale"

    if age_seconds > max_age_seconds:
        return "stale"

    return "fresh"


def _get_json(
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.RequestException as exc:
        raise FeedRequestError(
            "HTTP request failed: " + type(exc).__name__
        ) from exc

    try:
        payload = response.json()

    except ValueError as exc:
        raise FeedRequestError(
            "Provider returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise FeedDataError("Provider response is not a JSON object.")

    if response.status_code >= 400:
        provider_state = payload.get("data_state", {})
        provider_status = (
            provider_state.get("status", "unknown")
            if isinstance(provider_state, dict)
            else "unknown"
        )

        raise FeedRequestError(
            f"HTTP {response.status_code}; "
            f"provider_state={provider_status}"
        )

    return payload


def normalize_spot(
    payload: dict[str, Any],
    received_time: datetime | None = None,
) -> dict[str, Any]:
    """
    Normalize one XAU/USD reference spot response.

    The source timestamp is taken from price_as_of, falling back to
    data_state.as_of. updated_at is deliberately not used as a substitute
    for the actual price timestamp.
    """

    if not isinstance(payload, dict):
        raise FeedDataError("Spot payload must be an object.")

    received = received_time or _utc_now()

    state = payload.get("data_state")
    if not isinstance(state, dict):
        state = {}

    price = _positive_number(payload.get("spot_usd_oz"))

    if price is None:
        raise FeedDataError("Missing or invalid spot_usd_oz.")

    source_raw = (
        payload.get("price_as_of")
        or state.get("as_of")
    )

    source_time = _parse_timestamp(source_raw)

    age = _age_seconds(source_time, received)

    provider_status = str(
        state.get("status", "unknown")
    ).lower()

    explicit_stale = payload.get("stale") is True

    freshness = _freshness_status(
        provider_status=provider_status,
        age_seconds=age,
        max_age_seconds=SPOT_MAX_AGE_SECONDS,
        explicit_stale=explicit_stale,
    )

    return {
        "provider": "xaus.com",
        "instrument": "XAU/USD",
        "data_type": "spot_reference",
        "price_usd_per_troy_ounce": price,
        "source_timestamp": (
            _iso_utc(source_time) if source_time else None
        ),
        "received_at": _iso_utc(received),
        "source_age_seconds": (
            round(age, 2) if age is not None else None
        ),
        "provider_status": provider_status,
        "provider_source": state.get("source"),
        "freshness_status": freshness,
        "stale_flag": explicit_stale,
        "chart_type": "single_reference_value",
        "notice": (
            "Indicative mid-market reference data; "
            "not a guaranteed or tradable quote."
        ),
    }


def normalize_intraday(
    payload: dict[str, Any],
    received_time: datetime | None = None,
) -> dict[str, Any]:
    """
    Normalize sampled {t, p} price points.

    Output is a chronological point series suitable for a line chart.
    It never creates or estimates OHLC candles.
    """

    if not isinstance(payload, dict):
        raise FeedDataError("Intraday payload must be an object.")

    received = received_time or _utc_now()

    state = payload.get("data_state")
    if not isinstance(state, dict):
        state = {}

    raw_points = payload.get("points")

    if not isinstance(raw_points, list):
        raise FeedDataError("Intraday points must be a list.")

    provider_status = str(
        state.get("status", "unknown")
    ).lower()

    cleaned = []
    seen_timestamps = set()

    invalid_count = 0
    duplicate_count = 0
    future_count = 0
    order_valid = True

    previous_epoch = None

    for item in raw_points:

        if not isinstance(item, dict):
            invalid_count += 1
            continue

        point_time = _parse_timestamp(item.get("t"))
        point_price = _positive_number(item.get("p"))

        if point_time is None or point_price is None:
            invalid_count += 1
            continue

        epoch = point_time.timestamp()

        if epoch > received.timestamp() + 30:
            future_count += 1
            continue

        if previous_epoch is not None and epoch < previous_epoch:
            order_valid = False

        previous_epoch = epoch

        timestamp_key = round(epoch, 3)

        if timestamp_key in seen_timestamps:
            duplicate_count += 1
            continue

        seen_timestamps.add(timestamp_key)

        cleaned.append({
            "epoch_seconds": int(epoch),
            "t": _iso_utc(point_time),
            "p": point_price,
        })

    # Sort the validated points chronologically for chart presentation.
    cleaned.sort(key=lambda point: point["epoch_seconds"])

    latest_time = None

    if cleaned:
        latest_time = _parse_timestamp(cleaned[-1]["t"])

    age = _age_seconds(latest_time, received)

    if not cleaned:
        freshness = "unavailable"

    else:
        freshness = _freshness_status(
            provider_status=provider_status,
            age_seconds=age,
            max_age_seconds=INTRADAY_MAX_AGE_SECONDS,
            explicit_stale=False,
        )

    actual_coverage = None

    if len(cleaned) >= 2:
        first_time = _parse_timestamp(cleaned[0]["t"])
        last_time = _parse_timestamp(cleaned[-1]["t"])

        if first_time and last_time:
            actual_coverage = round(
                (last_time - first_time).total_seconds(),
                2,
            )

    source_coverage = payload.get("coverage_seconds")

    try:
        source_coverage = (
            float(source_coverage)
            if source_coverage is not None
            else None
        )

        if (
            source_coverage is not None
            and (
                not math.isfinite(source_coverage)
                or source_coverage < 0
            )
        ):
            source_coverage = None

    except (ValueError, TypeError, OverflowError):
        source_coverage = None

    quality_warnings = []

    if invalid_count:
        quality_warnings.append("invalid_points_removed")

    if duplicate_count:
        quality_warnings.append("duplicate_timestamps_removed")

    if future_count:
        quality_warnings.append("future_points_removed")

    if not order_valid:
        quality_warnings.append("source_order_was_not_chronological")

    return {
        "provider": "xaus.com",
        "instrument": "XAU/USD",
        "data_type": "sampled_spot_price_points",
        "chart_type": "line",
        "points": cleaned,
        "point_count": len(cleaned),
        "source_point_count": len(raw_points),
        "invalid_point_count": invalid_count,
        "duplicate_point_count": duplicate_count,
        "future_point_count": future_count,
        "source_order_valid": order_valid,
        "quality_warnings": quality_warnings,
        "source_coverage_seconds": source_coverage,
        "actual_coverage_seconds": actual_coverage,
        "latest_source_timestamp": (
            _iso_utc(latest_time) if latest_time else None
        ),
        "received_at": _iso_utc(received),
        "source_age_seconds": (
            round(age, 2) if age is not None else None
        ),
        "provider_status": provider_status,
        "provider_source": state.get("source"),
        "freshness_status": freshness,
        "notice": (
            "Sampled reference price points for line-chart display only. "
            "These points are not OHLC candles."
        ),
    }


def fetch_spot() -> dict[str, Any]:
    """
    Fetch one public spot reference response.
    No API key; no local persistence.
    """

    payload = _get_json(
        SPOT_URL,
        params={"compact": "1"},
    )

    return normalize_spot(payload)


def fetch_intraday(hours: int = 6) -> dict[str, Any]:
    """
    Fetch one sampled intraday point-series response.

    The provider accepts hours from 1 through 48.
    """

    if isinstance(hours, bool):
        raise ValueError("hours must be an integer from 1 to 48.")

    try:
        hours = int(hours)
    except (ValueError, TypeError):
        raise ValueError("hours must be an integer from 1 to 48.")

    if not 1 <= hours <= 48:
        raise ValueError("hours must be between 1 and 48.")

    payload = _get_json(
        INTRADAY_URL,
        params={
            "symbol": "xau",
            "hours": hours,
        },
    )

    return normalize_intraday(payload)
