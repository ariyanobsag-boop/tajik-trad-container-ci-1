
package com.xauusdpro.android.data

import kotlinx.serialization.json.JsonElement
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface MarketApi {

    @GET("health")
    suspend fun health(): JsonElement

    @GET("api/v1/unified/status")
    suspend fun getUnifiedStatus(): UnifiedMarketStatus

    @GET("api/v1/unified/latest")
    suspend fun getLatestCandle(): UnifiedCandle

    @GET("api/v1/unified/candles")
    suspend fun getCandles(
        @Query("limit") limit: Int = 100
    ): UnifiedCandlesResponse

    @GET("api/v1/unified/audit")
    suspend fun getAudit(): UnifiedAuditResponse

    @GET("api/v1/summary")
    suspend fun getSummary(): JsonElement

    @GET("api/v1/signals")
    suspend fun getSignals(): JsonElement

    @GET("api/v1/signals/{signal_id}")
    suspend fun getSignalDetail(
        @Path("signal_id") signalId: Int
    ): Response<JsonElement>

    @GET("api/v1/alerts")
    suspend fun getAlerts(): JsonElement
}
