package com.xauusdpro.android.data

import retrofit2.Call
import retrofit2.http.GET
import retrofit2.http.Query

interface MarketApi {

    @GET("health")
    fun health(): Call<ApiHealthResponse>

    @GET("api/v1/feed/spot")
    fun getSpot(): Call<SpotFeedResponse>

    @GET("api/v1/feed/intraday")
    fun getIntraday(
        @Query("hours") hours: Int = 6
    ): Call<IntradayFeedResponse>
}
