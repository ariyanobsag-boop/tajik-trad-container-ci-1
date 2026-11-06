"""Offline behavioral tests for TAJIK_TRAD read-only API."""

import sys
import types
import unittest
import threading
import time
import inspect

from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch


# Offline requests substitute
try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests.RequestException = RequestException

    def network_disabled(*args, **kwargs):
        raise AssertionError("Unexpected network request in API tests")

    requests.get = network_disabled
    sys.modules["requests"] = requests


# Minimal FastAPI substitute
fastapi_stub = types.ModuleType("fastapi")


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class FakeResponse:
    def __init__(self):
        self.headers = {}


class FakeQuery:
    def __init__(self, default=None, **options):
        self.default = default
        self.options = options


fastapi_stub.HTTPException = FakeHTTPException
fastapi_stub.Response = FakeResponse
fastapi_stub.Query = lambda default=None, **kw: FakeQuery(default, **kw)
sys.modules["fastapi"] = fastapi_stub

import xaus_readonly_api as api



def spot_payload():
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()

    return {
        "provider": "xaus.com",
        "instrument": "XAU/USD",
        "data_type": "spot_reference",
        "price_usd_per_troy_ounce": 4000.0,
        "source_timestamp": stamp,
        "received_at": stamp,
        "source_age_seconds": 0.0,
        "provider_status": "fresh",
        "provider_source": "test",
        "freshness_status": "fresh",
        "stale_flag": False,
        "chart_type": "single_reference_value",
        "notice": "Indicative reference data for testing.",
    }


def intraday_payload():
    now = datetime.now(timezone.utc)
    point_time = datetime.fromtimestamp(
        int(now.timestamp()),
        tz=timezone.utc,
    )
    stamp = point_time.isoformat()

    return {
        "provider": "xaus.com",
        "instrument": "XAU/USD",
        "data_type": "sampled_spot_price_points",
        "chart_type": "line",
        "points": [
            {
                "epoch_seconds": int(point_time.timestamp()),
                "t": stamp,
                "p": 4000.0,
            }
        ],
        "point_count": 1,
        "source_point_count": 1,
        "invalid_point_count": 0,
        "duplicate_point_count": 0,
        "future_point_count": 0,
        "source_order_valid": True,
        "quality_warnings": [],
        "source_coverage_seconds": None,
        "actual_coverage_seconds": None,
        "latest_source_timestamp": stamp,
        "received_at": now.isoformat(),
        "source_age_seconds": round(
            (now - point_time).total_seconds(),
            2,
        ),
        "provider_status": "fresh",
        "provider_source": "test",
        "freshness_status": "fresh",
        "notice": "Sampled reference points for testing.",
    }


def empty_intraday_payload():
    payload = intraday_payload()
    payload.update({
        "points": [],
        "point_count": 0,
        "source_point_count": 0,
        "latest_source_timestamp": None,
        "actual_coverage_seconds": None,
        "provider_status": "unavailable",
        "freshness_status": "unavailable",
    })
    return payload


def cached_fetch(key, fetcher, ttl=65.0):
    return api._cached_fetch(
        cache_key=key,
        fetcher=fetcher,
        cache_ttl=ttl,
        timestamp_field="source_timestamp",
        maximum_age=180,
    )


class FakeApp:
    def __init__(self, routes=None):
        self.routes = list(routes or [])

    def add_api_route(self, path, endpoint, **kwargs):
        self.routes.append(
            SimpleNamespace(path=path, endpoint=endpoint, **kwargs)
        )


class TestCacheLifecycle(unittest.TestCase):

    def setUp(self):
        api.clear_readonly_cache()

    def test_first_request_miss_second_request_hit(self):
        calls = []

        def fetch():
            calls.append(1)
            return spot_payload()

        first = cached_fetch("test-miss-hit", fetch)
        second = cached_fetch("test-miss-hit", fetch)

        self.assertEqual(first["server_cache_status"], "miss")
        self.assertEqual(second["server_cache_status"], "hit")
        self.assertEqual(len(calls), 1)

    def test_expired_entry_is_refetched(self):
        clock = [100.0]
        calls = []

        def fetch():
            calls.append(1)
            return spot_payload()

        with patch.object(api, "monotonic", side_effect=lambda: clock[0]):
            cached_fetch("test-expiry", fetch, ttl=10)
            clock[0] = 111.0
            result = cached_fetch("test-expiry", fetch, ttl=10)

        self.assertEqual(result["server_cache_status"], "miss")
        self.assertEqual(len(calls), 2)

    def test_exact_ttl_boundary_is_expired(self):
        clock = [100.0]
        calls = []

        def fetch():
            calls.append(1)
            return spot_payload()

        with patch.object(api, "monotonic", side_effect=lambda: clock[0]):
            cached_fetch("test-boundary", fetch, ttl=10)
            clock[0] = 110.0
            result = cached_fetch("test-boundary", fetch, ttl=10)

        self.assertEqual(result["server_cache_status"], "miss")
        self.assertEqual(len(calls), 2)

    def test_cached_data_is_deep_copied(self):
        original = spot_payload()
        original["nested"] = {"value": 10}

        first = cached_fetch("test-copy", lambda: original)
        original["nested"]["value"] = 99
        first["nested"]["value"] = 77

        second = cached_fetch(
            "test-copy",
            lambda: self.fail("Unexpected second fetch"),
        )

        self.assertEqual(second["nested"]["value"], 10)

    def test_freshness_is_recalculated_on_cache_hit(self):
        base = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
        payload = {
            "price": 4000.0,
            "source_timestamp": base.isoformat(),
            "provider_status": "fresh",
            "received_at": base.isoformat(),
        }

        with patch.object(
            api,
            "_utc_now",
            side_effect=[base, base + timedelta(seconds=20)],
        ):
            first = cached_fetch("test-age", lambda: payload)
            second = cached_fetch("test-age", lambda: payload)

        self.assertEqual(first["source_age_seconds"], 0.0)
        self.assertEqual(second["source_age_seconds"], 20.0)
        self.assertEqual(second["server_cache_status"], "hit")

    def test_clear_cache_removes_entry(self):
        cached_fetch("test-clear", spot_payload)
        self.assertIn("test-clear", api._CACHE)

        api.clear_readonly_cache()

        self.assertNotIn("test-clear", api._CACHE)

    def test_expired_entry_is_not_served_when_refresh_fails(self):
        clock = [100.0]

        with patch.object(api, "monotonic", side_effect=lambda: clock[0]):
            cached_fetch("test-stale-error", spot_payload, ttl=5)
            clock[0] = 106.0

            with self.assertRaises(api.HTTPException) as caught:
                cached_fetch(
                    "test-stale-error",
                    lambda: (_ for _ in ()).throw(
                        api.feed.FeedRequestError("simulated outage")
                    ),
                    ttl=5,
                )

        self.assertEqual(caught.exception.status_code, 503)


class TestErrorHandling(unittest.TestCase):

    def setUp(self):
        api.clear_readonly_cache()

    def test_request_error_maps_to_503(self):
        def fetch():
            raise api.feed.FeedRequestError("simulated network failure")

        with self.assertRaises(api.HTTPException) as caught:
            cached_fetch("test-request-error", fetch)

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(
            caught.exception.detail["error"],
            "upstream_unavailable",
        )
        self.assertNotIn("error_type", caught.exception.detail)
        self.assertNotIn(
            "simulated network failure",
            str(caught.exception.detail),
        )

    def test_provider_data_error_maps_to_502(self):
        def fetch():
            raise api.feed.FeedDataError("simulated invalid data")

        with self.assertRaises(api.HTTPException) as caught:
            cached_fetch("test-data-error", fetch)

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(
            caught.exception.detail["error"],
            "invalid_provider_data",
        )
        self.assertNotIn("error_type", caught.exception.detail)
        self.assertNotIn(
            "simulated invalid data",
            str(caught.exception.detail),
        )

    def test_unexpected_error_is_logged_without_disclosure(self):
        def fetch():
            raise RuntimeError("private internal message")

        with patch.object(api, "logger", create=True) as logger:
            with self.assertRaises(api.HTTPException) as caught:
                cached_fetch("test-internal-error", fetch)

            logger.exception.assert_called_once()

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(
            caught.exception.detail["error"],
            "feed_processing_failed",
        )
        self.assertNotIn("error_type", caught.exception.detail)
        self.assertNotIn(
            "private internal message",
            str(caught.exception.detail),
        )

    def test_non_dictionary_payload_is_rejected(self):
        with self.assertRaises(api.HTTPException) as caught:
            cached_fetch("test-non-dict", lambda: ["invalid"])

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(
            caught.exception.detail["error"],
            "invalid_normalized_payload",
        )
        self.assertNotIn("test-non-dict", api._CACHE)

    def test_failed_fetch_is_not_cached_and_can_recover(self):
        calls = []

        def fetch():
            calls.append(1)
            if len(calls) == 1:
                raise api.feed.FeedRequestError("temporary failure")
            return spot_payload()

        with self.assertRaises(api.HTTPException):
            cached_fetch("test-recovery", fetch)

        result = cached_fetch("test-recovery", fetch)

        self.assertEqual(result["server_cache_status"], "miss")
        self.assertEqual(len(calls), 2)



class TestPayloadAndCacheHardening(unittest.TestCase):

    def setUp(self):
        api.clear_readonly_cache()

    def test_empty_intraday_response_bypasses_cache(self):
        calls = []

        def fetch():
            calls.append(1)
            return empty_intraday_payload()

        first = api._cached_fetch(
            "intraday:test-empty",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )
        second = api._cached_fetch(
            "intraday:test-empty",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )

        self.assertEqual(first["freshness_status"], "unavailable")
        self.assertEqual(second["freshness_status"], "unavailable")
        self.assertEqual(first["server_cache_status"], "bypass")
        self.assertEqual(second["server_cache_status"], "bypass")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("intraday:test-empty", api._CACHE)

    def test_unavailable_intraday_with_points_bypasses_cache(self):
        calls = []
        payload = intraday_payload()
        payload["provider_status"] = "unavailable"
        payload["freshness_status"] = "unavailable"

        def fetch():
            calls.append(1)
            return payload

        first = api._cached_fetch(
            "intraday:test-unavailable",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )
        second = api._cached_fetch(
            "intraday:test-unavailable",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )

        self.assertEqual(first["server_cache_status"], "bypass")
        self.assertEqual(second["server_cache_status"], "bypass")
        self.assertEqual(len(calls), 2)
        self.assertNotIn("intraday:test-unavailable", api._CACHE)

    def test_empty_response_allows_immediate_recovery(self):
        calls = []
        responses = [
            empty_intraday_payload(),
            intraday_payload(),
        ]

        def fetch():
            calls.append(1)
            return responses.pop(0)

        first = api._cached_fetch(
            "intraday:test-recovery",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )
        second = api._cached_fetch(
            "intraday:test-recovery",
            fetch,
            305,
            "latest_source_timestamp",
            600,
        )

        self.assertEqual(first["server_cache_status"], "bypass")
        self.assertEqual(second["server_cache_status"], "miss")
        self.assertEqual(second["freshness_status"], "fresh")
        self.assertEqual(len(calls), 2)
        self.assertIn("intraday:test-recovery", api._CACHE)

    def test_empty_refresh_removes_expired_entry(self):
        clock = [100.0]

        with patch.object(api, "monotonic", side_effect=lambda: clock[0]):
            api._cached_fetch(
                "intraday:test-expired-empty",
                intraday_payload,
                10,
                "latest_source_timestamp",
                600,
            )

            self.assertIn("intraday:test-expired-empty", api._CACHE)

            clock[0] = 111.0

            result = api._cached_fetch(
                "intraday:test-expired-empty",
                empty_intraday_payload,
                10,
                "latest_source_timestamp",
                600,
            )

        self.assertEqual(result["server_cache_status"], "bypass")
        self.assertNotIn("intraday:test-expired-empty", api._CACHE)

    def test_arbitrary_dictionary_is_rejected_and_not_cached(self):
        with self.assertRaises(api.HTTPException) as caught:
            cached_fetch(
                "test-arbitrary-dict",
                lambda: {"unexpected_field": "value"},
            )

        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(
            caught.exception.detail["error"],
            "invalid_normalized_payload",
        )
        self.assertNotIn("test-arbitrary-dict", api._CACHE)

    def test_valid_normalized_spot_payload_is_accepted(self):
        result = cached_fetch(
            "test-valid-spot",
            spot_payload,
        )

        self.assertEqual(result["data_type"], "spot_reference")
        self.assertEqual(
            result["price_usd_per_troy_ounce"],
            4000.0,
        )
        self.assertIn("test-valid-spot", api._CACHE)

    def test_valid_normalized_intraday_payload_is_accepted(self):
        result = api._cached_fetch(
            "intraday:test-valid",
            intraday_payload,
            305,
            "latest_source_timestamp",
            600,
        )

        self.assertEqual(
            result["data_type"],
            "sampled_spot_price_points",
        )
        self.assertEqual(result["point_count"], 1)
        self.assertIn("intraday:test-valid", api._CACHE)

    def test_spot_rejects_invalid_prices_without_caching(self):
        invalid_prices = [
            0,
            -1,
            True,
            float("nan"),
            float("inf"),
        ]

        for index, invalid_price in enumerate(invalid_prices):
            with self.subTest(price=invalid_price):
                payload = spot_payload()
                payload["price_usd_per_troy_ounce"] = invalid_price
                key = f"spot:test-invalid-price-{index}"

                with self.assertRaises(api.HTTPException) as caught:
                    api._cached_fetch(
                        key,
                        lambda value=payload: value,
                        65,
                        "source_timestamp",
                        180,
                    )

                self.assertEqual(caught.exception.status_code, 502)
                self.assertNotIn(key, api._CACHE)

    def test_spot_requires_normalized_metadata(self):
        payload = spot_payload()
        del payload["instrument"]

        with self.assertRaises(api.HTTPException) as caught:
            api._cached_fetch(
                "spot:test-missing-metadata",
                lambda: payload,
                65,
                "source_timestamp",
                180,
            )

        self.assertEqual(
            caught.exception.detail["error"],
            "invalid_normalized_payload",
        )
        self.assertNotIn("spot:test-missing-metadata", api._CACHE)

    def test_intraday_rejects_invalid_point_without_caching(self):
        payload = intraday_payload()
        payload["points"][0]["p"] = 0

        with self.assertRaises(api.HTTPException):
            api._cached_fetch(
                "intraday:test-invalid-point",
                lambda: payload,
                305,
                "latest_source_timestamp",
                600,
            )

        self.assertNotIn("intraday:test-invalid-point", api._CACHE)

    def test_intraday_rejects_inconsistent_point_count(self):
        payload = intraday_payload()
        payload["point_count"] = 2

        with self.assertRaises(api.HTTPException):
            api._cached_fetch(
                "intraday:test-count-mismatch",
                lambda: payload,
                305,
                "latest_source_timestamp",
                600,
            )

        self.assertNotIn("intraday:test-count-mismatch", api._CACHE)

    def test_intraday_rejects_invalid_point_timestamp(self):
        payload = intraday_payload()
        payload["points"][0]["t"] = "not-a-timestamp"

        with self.assertRaises(api.HTTPException):
            api._cached_fetch(
                "intraday:test-invalid-timestamp",
                lambda: payload,
                305,
                "latest_source_timestamp",
                600,
            )

        self.assertNotIn("intraday:test-invalid-timestamp", api._CACHE)

    def test_intraday_enforces_maximum_point_count(self):
        payload = intraday_payload()
        payload["points"] = [{}] * (
            api.feed.MAX_INTRADAY_POINTS + 1
        )
        payload["point_count"] = len(payload["points"])
        payload["source_point_count"] = len(payload["points"])

        with self.assertRaises(api.HTTPException):
            api._cached_fetch(
                "intraday:test-too-many-points",
                lambda: payload,
                305,
                "latest_source_timestamp",
                600,
            )

        self.assertNotIn("intraday:test-too-many-points", api._CACHE)


class TestConcurrency(unittest.TestCase):

    def setUp(self):
        api.clear_readonly_cache()

    def test_parallel_requests_same_key_fetch_once(self):
        count = [0]
        count_lock = threading.Lock()

        def fetch():
            with count_lock:
                count[0] += 1
            time.sleep(0.04)
            return spot_payload()

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: cached_fetch("test-parallel-same", fetch),
                    range(8),
                )
            )

        self.assertEqual(count[0], 1)
        self.assertEqual(
            sum(r["server_cache_status"] == "miss" for r in results),
            1,
        )
        self.assertEqual(
            sum(r["server_cache_status"] == "hit" for r in results),
            7,
        )

    def test_different_keys_can_fetch_in_parallel(self):
        barrier = threading.Barrier(2)

        def fetch():
            barrier.wait(timeout=3)
            return spot_payload()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                cached_fetch, "test-parallel-a", fetch
            )
            second = pool.submit(
                cached_fetch, "test-parallel-b", fetch
            )
            result_a = first.result(timeout=5)
            result_b = second.result(timeout=5)

        self.assertEqual(result_a["server_cache_status"], "miss")
        self.assertEqual(result_b["server_cache_status"], "miss")


    def test_clear_during_fetch_prevents_cache_repopulation(self):
        started = threading.Event()
        release = threading.Event()

        def slow_fetch():
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test synchronization timeout")
            return spot_payload()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                cached_fetch,
                "test-clear-race",
                slow_fetch,
            )

            self.assertTrue(started.wait(timeout=3))
            api.clear_readonly_cache()
            self.assertNotIn("test-clear-race", api._CACHE)

            release.set()
            result = future.result(timeout=5)

        self.assertEqual(result["server_cache_status"], "bypass")
        self.assertNotIn("test-clear-race", api._CACHE)


class TestRoutes(unittest.TestCase):

    def setUp(self):
        api.clear_readonly_cache()

    def test_registers_only_two_get_routes(self):
        app = FakeApp()
        handlers = api.register_xaus_readonly_routes(app)

        self.assertEqual(
            {route.path for route in app.routes},
            {
                "/api/v1/feed/spot",
                "/api/v1/feed/intraday",
            },
        )
        self.assertEqual(len(app.routes), 2)

        for route in app.routes:
            self.assertEqual(route.methods, ["GET"])

        self.assertEqual(set(handlers), {"spot", "intraday"})

    def test_invalid_application_is_rejected(self):
        with self.assertRaises(RuntimeError):
            api.register_xaus_readonly_routes(None)

    def test_existing_route_conflict_is_rejected(self):
        app = FakeApp([
            SimpleNamespace(path="/api/v1/feed/spot")
        ])

        with self.assertRaises(RuntimeError):
            api.register_xaus_readonly_routes(app)

        self.assertEqual(len(app.routes), 1)

    def test_spot_route_sets_no_store_headers(self):
        app = FakeApp()
        handlers = api.register_xaus_readonly_routes(app)
        response = api.Response()

        with patch.object(
            api.feed, "fetch_spot", return_value=spot_payload()
        ):
            result = handlers["spot"](response)

        self.assertEqual(
            response.headers["Cache-Control"],
            "no-store, max-age=0",
        )
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertIn("server_cache_status", result)

    def test_intraday_query_has_expected_limits(self):
        app = FakeApp()
        handlers = api.register_xaus_readonly_routes(app)

        parameter = inspect.signature(
            handlers["intraday"]
        ).parameters["hours"].default

        self.assertEqual(parameter.default, 6)
        self.assertEqual(parameter.options.get("ge"), 1)
        self.assertEqual(parameter.options.get("le"), 48)

    def test_intraday_cache_keys_are_separate_by_hours(self):
        app = FakeApp()
        handlers = api.register_xaus_readonly_routes(app)
        response = api.Response()

        with patch.object(
            api.feed,
            "fetch_intraday",
            return_value=intraday_payload(),
        ) as fetch:
            handlers["intraday"](response, hours=6)
            handlers["intraday"](response, hours=6)
            handlers["intraday"](response, hours=12)

        self.assertEqual(fetch.call_count, 2)

    def test_spot_headers_are_set_even_when_fetch_fails(self):
        app = FakeApp()
        handlers = api.register_xaus_readonly_routes(app)
        response = api.Response()

        with patch.object(
            api.feed,
            "fetch_spot",
            side_effect=api.feed.FeedRequestError("simulated outage"),
        ):
            with self.assertRaises(api.HTTPException):
                handlers["spot"](response)

        self.assertEqual(
            response.headers["Cache-Control"],
            "no-store, max-age=0",
        )
        self.assertEqual(response.headers["Pragma"], "no-cache")


if __name__ == "__main__":
    unittest.main(verbosity=2)
