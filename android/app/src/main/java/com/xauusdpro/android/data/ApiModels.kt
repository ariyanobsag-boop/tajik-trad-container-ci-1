
package com.xauusdpro.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Serializable
data class UnifiedMarketStatus(
    @SerialName("service")
    val service: String? = null,

    @SerialName("active_provider")
    val activeProvider: String,

    @SerialName("source_symbol")
    val sourceSymbol: String,

    @SerialName("requested_instrument")
    val requestedInstrument: String,

    @SerialName("timeframe")
    val timeframe: String,

    @SerialName("market_type")
    val marketType: String,

    @SerialName("identity_status")
    val identityStatus: String,

    @SerialName("spot_identity_verified")
    val spotIdentityVerified: Boolean,

    @SerialName("mode")
    val mode: String,

    @SerialName("live_connection")
    val liveConnection: Boolean,

    @SerialName("broker_connection")
    val brokerConnection: Boolean,

    @SerialName("automatic_execution")
    val automaticExecution: Boolean
)

@Serializable
data class CandleSource(
    @SerialName("provider")
    val provider: String,

    @SerialName("source_symbol")
    val sourceSymbol: String,

    @SerialName("requested_instrument")
    val requestedInstrument: String,

    @SerialName("market_type")
    val marketType: String,

    @SerialName("identity_status")
    val identityStatus: String,

    @SerialName("spot_identity_verified")
    val spotIdentityVerified: Boolean
)

@Serializable
data class UnifiedCandle(
    val timestamp: String,
    val timeframe: String,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double? = null,

    @SerialName("tick_volume")
    val tickVolume: Double? = null,

    val source: CandleSource
)

@Serializable
data class CandleAuditSummary(
    @SerialName("candles_received")
    val candlesReceived: Int,

    @SerialName("duplicate_timestamps")
    val duplicateTimestamps: Int,

    @SerialName("out_of_order_intervals")
    val outOfOrderIntervals: Int,

    @SerialName("gaps_over_expected")
    val gapsOverExpected: Int,

    @SerialName("non_standard_intervals")
    val nonStandardIntervals: Int,

    @SerialName("expected_interval_seconds")
    val expectedIntervalSeconds: Int,

    @SerialName("strictly_ordered")
    val strictlyOrdered: Boolean
)

@Serializable
data class UnifiedCandlesResponse(
    val status: String,

    @SerialName("provider_status")
    val providerStatus: UnifiedMarketStatus,

    val summary: CandleAuditSummary,
    val candles: List<UnifiedCandle>
)

@Serializable
data class UnifiedAuditResponse(
    @SerialName("provider_status")
    val providerStatus: UnifiedMarketStatus,

    val summary: CandleAuditSummary,

    @SerialName("candles_received")
    val candlesReceived: Int
)

// Legacy endpoints may evolve independently.
// JsonElement preserves their complete response without
// making unsupported assumptions about their fields.

@Serializable
data class GenericApiError(
    val detail: JsonElement? = null
)

@Serializable
data class ApiHealthResponse(
    val status: String? = null
)
