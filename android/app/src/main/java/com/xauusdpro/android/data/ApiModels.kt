package com.xauusdpro.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class SpotFeedResponse(
    val provider: String,
    val instrument: String,

    @SerialName("data_type")
    val dataType: String,

    @SerialName("price_usd_per_troy_ounce")
    val priceUsdPerTroyOunce: Double,

    @SerialName("source_timestamp")
    val sourceTimestamp: String? = null,

    @SerialName("received_at")
    val receivedAt: String,

    @SerialName("source_age_seconds")
    val sourceAgeSeconds: Double? = null,

    @SerialName("provider_status")
    val providerStatus: String,

    @SerialName("provider_source")
    val providerSource: JsonElement? = null,

    @SerialName("freshness_status")
    val freshnessStatus: String,

    @SerialName("stale_flag")
    val staleFlag: Boolean,

    @SerialName("chart_type")
    val chartType: String,

    val notice: String,

    @SerialName("served_at")
    val servedAt: String? = null,

    @SerialName("provider_received_at")
    val providerReceivedAt: String? = null,

    @SerialName("server_cache_status")
    val serverCacheStatus: String? = null,

    @SerialName("server_cache_age_seconds")
    val serverCacheAgeSeconds: Double? = null,

    @SerialName("server_cache_ttl_seconds")
    val serverCacheTtlSeconds: Double? = null
)

@Serializable
data class IntradayPricePoint(
    @SerialName("epoch_seconds")
    val epochSeconds: Long,

    val t: String,
    val p: Double
)

@Serializable
data class IntradayFeedResponse(
    val provider: String,
    val instrument: String,

    @SerialName("data_type")
    val dataType: String,

    @SerialName("chart_type")
    val chartType: String,

    val points: List<IntradayPricePoint>,

    @SerialName("point_count")
    val pointCount: Int,

    @SerialName("source_point_count")
    val sourcePointCount: Int,

    @SerialName("invalid_point_count")
    val invalidPointCount: Int,

    @SerialName("duplicate_point_count")
    val duplicatePointCount: Int,

    @SerialName("future_point_count")
    val futurePointCount: Int,

    @SerialName("source_order_valid")
    val sourceOrderValid: Boolean,

    @SerialName("quality_warnings")
    val qualityWarnings: List<String>,

    @SerialName("source_coverage_seconds")
    val sourceCoverageSeconds: Double? = null,

    @SerialName("actual_coverage_seconds")
    val actualCoverageSeconds: Double? = null,

    @SerialName("latest_source_timestamp")
    val latestSourceTimestamp: String? = null,

    @SerialName("received_at")
    val receivedAt: String,

    @SerialName("source_age_seconds")
    val sourceAgeSeconds: Double? = null,

    @SerialName("provider_status")
    val providerStatus: String,

    @SerialName("provider_source")
    val providerSource: JsonElement? = null,

    @SerialName("freshness_status")
    val freshnessStatus: String,

    val notice: String,

    @SerialName("served_at")
    val servedAt: String? = null,

    @SerialName("provider_received_at")
    val providerReceivedAt: String? = null,

    @SerialName("server_cache_status")
    val serverCacheStatus: String? = null,

    @SerialName("server_cache_age_seconds")
    val serverCacheAgeSeconds: Double? = null,

    @SerialName("server_cache_ttl_seconds")
    val serverCacheTtlSeconds: Double? = null
)

@Serializable
data class GenericApiError(
    val detail: JsonElement? = null
)

@Serializable
data class ApiHealthResponse(
    val status: String? = null,
    val service: String? = null
)
