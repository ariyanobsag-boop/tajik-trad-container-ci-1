import sys
import types
import unittest
from datetime import datetime, timezone

# Allow offline testing when requests is not installed.
try:
    import requests
except ModuleNotFoundError:
    requests = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    requests.RequestException = RequestException

    def network_disabled(*args, **kwargs):
        raise AssertionError("Unexpected network request in unit tests")

    requests.get = network_disabled
    sys.modules["requests"] = requests

import xaus_readonly_feed as feed


class TestTimestampParsing(unittest.TestCase):

    def test_unix_seconds(self):
        result = feed._parse_timestamp(1704067200)
        self.assertEqual(
            result,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_unix_milliseconds(self):
        result = feed._parse_timestamp(1704067200000)
        self.assertEqual(
            result,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_iso_timestamp(self):
        result = feed._parse_timestamp("2024-01-01T00:00:00Z")
        self.assertEqual(
            result,
            datetime(2024, 1, 1, tzinfo=timezone.utc),
        )

    def test_naive_timestamp_is_treated_as_utc(self):
        result = feed._parse_timestamp("2024-01-01T00:00:00")
        self.assertEqual(result.utcoffset().total_seconds(), 0)

    def test_invalid_timestamps_are_rejected(self):
        invalid_values = [
            None,
            True,
            float("nan"),
            float("inf"),
            "not-a-date",
            "",
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(feed._parse_timestamp(value))


class TestPositiveNumber(unittest.TestCase):

    def test_valid_positive_number(self):
        self.assertEqual(feed._positive_number(4000), 4000.0)
        self.assertEqual(feed._positive_number("12.5"), 12.5)

    def test_invalid_numbers_are_rejected(self):
        invalid_values = [
            None,
            True,
            False,
            0,
            -1,
            "invalid",
            float("nan"),
            float("inf"),
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(feed._positive_number(value))


class TestFreshness(unittest.TestCase):

    def test_fresh_data(self):
        self.assertEqual(
            feed._freshness_status("fresh", 30, 180),
            "fresh",
        )

    def test_old_data_is_stale(self):
        self.assertEqual(
            feed._freshness_status("fresh", 181, 180),
            "stale",
        )

    def test_unknown_provider_state_is_stale(self):
        self.assertEqual(
            feed._freshness_status("unknown", 10, 180),
            "stale",
        )

    def test_unavailable_provider_state(self):
        self.assertEqual(
            feed._freshness_status("unavailable", None, 180),
            "unavailable",
        )

    def test_explicit_stale_flag(self):
        self.assertEqual(
            feed._freshness_status("fresh", 10, 180, True),
            "stale",
        )


class TestSpotNormalization(unittest.TestCase):

    def setUp(self):
        self.received = datetime(
            2026, 1, 1, 0, 1, 0,
            tzinfo=timezone.utc,
        )

    def test_valid_spot_data(self):
        payload = {
            "spot_usd_oz": 4000,
            "price_as_of": "2026-01-01T00:00:30Z",
            "data_state": {
                "status": "fresh",
                "source": "test-provider",
            },
        }

        result = feed.normalize_spot(
            payload,
            received_time=self.received,
        )

        self.assertEqual(
            result["price_usd_per_troy_ounce"],
            4000.0,
        )
        self.assertEqual(result["freshness_status"], "fresh")
        self.assertEqual(result["source_age_seconds"], 30.0)
        self.assertEqual(result["provider"], "xaus.com")

    def test_timestamp_fallback(self):
        payload = {
            "spot_usd_oz": 4000,
            "data_state": {
                "status": "fresh",
                "as_of": "2026-01-01T00:01:00Z",
            },
        }

        result = feed.normalize_spot(
            payload,
            received_time=self.received,
        )

        self.assertEqual(result["source_age_seconds"], 0.0)
        self.assertEqual(result["freshness_status"], "fresh")

    def test_invalid_spot_prices_are_rejected(self):
        invalid_values = [
            None,
            True,
            0,
            -1,
            "invalid",
            float("nan"),
            float("inf"),
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(feed.FeedDataError):
                    feed.normalize_spot(
                        {
                            "spot_usd_oz": value,
                            "data_state": {"status": "fresh"},
                        },
                        received_time=self.received,
                    )


class TestIntradayNormalization(unittest.TestCase):

    def setUp(self):
        self.received = datetime(
            2026, 1, 1, 0, 10, 0,
            tzinfo=timezone.utc,
        )

    def test_points_are_sorted_chronologically(self):
        payload = {
            "data_state": {"status": "fresh"},
            "points": [
                {"t": "2026-01-01T00:09:40Z", "p": 4002},
                {"t": "2026-01-01T00:09:20Z", "p": 4001},
            ],
        }

        result = feed.normalize_intraday(
            payload,
            received_time=self.received,
        )

        self.assertEqual(
            [point["p"] for point in result["points"]],
            [4001.0, 4002.0],
        )
        self.assertFalse(result["source_order_valid"])
        self.assertEqual(result["freshness_status"], "fresh")

    def test_invalid_duplicate_and_future_points(self):
        payload = {
            "data_state": {"status": "fresh"},
            "points": [
                "not-an-object",
                {"t": "invalid-time", "p": 4000},
                {"t": "2026-01-01T00:09:55Z", "p": -1},
                {"t": "2026-01-01T00:09:50Z", "p": 4001},
                {"t": "2026-01-01T00:09:50Z", "p": 4002},
                {"t": "2026-01-01T00:10:31Z", "p": 4003},
            ],
        }

        result = feed.normalize_intraday(
            payload,
            received_time=self.received,
        )

        self.assertEqual(result["invalid_point_count"], 3)
        self.assertEqual(result["duplicate_point_count"], 1)
        self.assertEqual(result["future_point_count"], 1)
        self.assertEqual(result["point_count"], 1)

    def test_empty_points_are_unavailable(self):
        result = feed.normalize_intraday(
            {
                "data_state": {"status": "fresh"},
                "points": [],
            },
            received_time=self.received,
        )

        self.assertEqual(result["point_count"], 0)
        self.assertEqual(result["freshness_status"], "unavailable")

    def test_missing_points_are_rejected(self):
        with self.assertRaises(feed.FeedDataError):
            feed.normalize_intraday(
                {"data_state": {"status": "fresh"}},
                received_time=self.received,
            )





class TestIntradayPointLimit(unittest.TestCase):
    def setUp(self):
        self.received = datetime(
            2026, 1, 1, 0, 10, 0,
            tzinfo=timezone.utc,
        )

    def test_rejects_more_than_1500_raw_points(self):
        payload = {
            "data_state": {"status": "fresh"},
            "points": [None] * 1501,
        }

        with self.assertRaises(feed.FeedDataError):
            feed.normalize_intraday(
                payload,
                received_time=self.received,
            )

    def test_accepts_exactly_1500_raw_points(self):
        payload = {
            "data_state": {"status": "fresh"},
            "points": [None] * 1500,
        }

        result = feed.normalize_intraday(
            payload,
            received_time=self.received,
        )

        self.assertEqual(result["source_point_count"], 1500)
        self.assertEqual(result["point_count"], 0)


class FakeStreamingResponse:
    def __init__(self, chunks):
        self.chunks = chunks
        self.status_code = 200
        self.chunks_read = 0
        self.closed = False

    def iter_content(self, chunk_size=65536):
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk

    def json(self):
        return {"legacy_json_method": True}

    def close(self):
        self.closed = True


class TestGetJsonResponseSizeLimit(unittest.TestCase):
    MAX_BYTES = 1_048_576

    def test_accepts_response_exactly_at_1_mib_limit(self):
        from unittest.mock import patch

        prefix = b'{"ok":true}'
        body = prefix + b" " * (self.MAX_BYTES - len(prefix))
        chunks = [
            body[index:index + 65536]
            for index in range(0, len(body), 65536)
        ]
        response = FakeStreamingResponse(chunks)

        with patch.object(
            feed.requests,
            "get",
            return_value=response,
        ) as mocked_get:
            result = feed._get_json(
                "https://example.invalid",
                params={},
            )

        self.assertEqual(result, {"ok": True})
        self.assertTrue(mocked_get.call_args.kwargs.get("stream"))
        self.assertTrue(response.closed)

    def test_rejects_response_larger_than_1_mib_limit(self):
        from unittest.mock import patch

        response = FakeStreamingResponse([
            b" " * self.MAX_BYTES,
            b"x",
            b"unread-extra-data",
        ])

        with patch.object(
            feed.requests,
            "get",
            return_value=response,
        ) as mocked_get:
            with self.assertRaises(feed.FeedRequestError):
                feed._get_json(
                    "https://example.invalid",
                    params={},
                )

        self.assertTrue(mocked_get.call_args.kwargs.get("stream"))
        self.assertEqual(response.chunks_read, 2)
        self.assertTrue(response.closed)


class InterruptingStreamingResponse(FakeStreamingResponse):
    def __init__(self, chunks, stream_error):
        super().__init__(chunks)
        self.stream_error = stream_error

    def iter_content(self, chunk_size=65536):
        yield from super().iter_content(chunk_size)
        raise self.stream_error


class TestGetJsonErrorHandling(unittest.TestCase):

    def test_empty_and_malformed_json_are_rejected_and_closed(self):
        from unittest.mock import patch

        for body in (b"", b"{"):
            with self.subTest(body_length=len(body)):
                response = FakeStreamingResponse([body])

                with patch.object(
                    feed.requests,
                    "get",
                    return_value=response,
                ):
                    with self.assertRaises(feed.FeedRequestError):
                        feed._get_json(
                            "https://example.invalid",
                            params={},
                        )

                self.assertTrue(response.closed)

    def test_non_object_json_is_rejected_and_closed(self):
        from unittest.mock import patch

        response = FakeStreamingResponse([b"[1, 2, 3]"])

        with patch.object(
            feed.requests,
            "get",
            return_value=response,
        ):
            with self.assertRaises(feed.FeedDataError):
                feed._get_json(
                    "https://example.invalid",
                    params={},
                )

        self.assertTrue(response.closed)

    def test_http_errors_preserve_status_and_provider_state(self):
        from unittest.mock import patch

        body = b'{"data_state":{"status":"unavailable"}}'

        for status in (404, 500, 503):
            with self.subTest(status=status):
                response = FakeStreamingResponse([body])
                response.status_code = status

                with patch.object(
                    feed.requests,
                    "get",
                    return_value=response,
                ):
                    with self.assertRaises(feed.FeedRequestError) as caught:
                        feed._get_json(
                            "https://example.invalid",
                            params={},
                        )

                self.assertIn(f"HTTP {status}", str(caught.exception))
                self.assertIn("provider_state=unavailable", str(caught.exception))
                self.assertTrue(response.closed)

    def test_request_failure_is_normalized(self):
        from unittest.mock import patch

        failure = feed.requests.RequestException("network unavailable")

        with patch.object(
            feed.requests,
            "get",
            side_effect=failure,
        ):
            with self.assertRaises(feed.FeedRequestError) as caught:
                feed._get_json(
                    "https://example.invalid",
                    params={},
                )

        self.assertIn("RequestException", str(caught.exception))

    def test_stream_failure_is_normalized_and_response_closed(self):
        from unittest.mock import patch

        failure = feed.requests.RequestException("connection interrupted")
        response = InterruptingStreamingResponse(
            [b'{"ok":'],
            failure,
        )

        with patch.object(
            feed.requests,
            "get",
            return_value=response,
        ):
            with self.assertRaises(feed.FeedRequestError) as caught:
                feed._get_json(
                    "https://example.invalid",
                    params={},
                )

        self.assertIn("RequestException", str(caught.exception))
        self.assertTrue(response.closed)

    def test_request_uses_configured_timeout_and_streaming(self):
        from unittest.mock import patch

        response = FakeStreamingResponse([b'{"ok":true}'])

        with patch.object(
            feed.requests,
            "get",
            return_value=response,
        ) as mocked_get:
            result = feed._get_json(
                "https://example.invalid",
                params={"symbol": "xau"},
            )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            mocked_get.call_args.kwargs["timeout"],
            feed.REQUEST_TIMEOUT,
        )
        self.assertTrue(mocked_get.call_args.kwargs["stream"])
        self.assertEqual(
            mocked_get.call_args.kwargs["params"],
            {"symbol": "xau"},
        )
        self.assertTrue(response.closed)


class TestIntradayRequestValidation(unittest.TestCase):

    def test_fractional_hours_are_rejected(self):
        from unittest.mock import patch

        payload = {
            "data_state": {"status": "unavailable"},
            "points": [],
        }

        with patch.object(
            feed,
            "_get_json",
            return_value=payload,
        ) as mocked_fetch:

            with self.assertRaises(ValueError):
                feed.fetch_intraday(1.9)

            mocked_fetch.assert_not_called()

if __name__ == "__main__":
    unittest.main(verbosity=2)
