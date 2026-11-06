package com.xauusdpro.android.data

import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.MediaType.Companion.toMediaType
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.net.URI
import java.util.concurrent.TimeUnit

object MarketApiFactory {

    private val contentType =
        "application/json; charset=utf-8".toMediaType()

    fun create(baseUrl: String): MarketApi {
        val normalized = baseUrl.trim()

        require(normalized.endsWith("/")) {
            "Base URL must end with '/'."
        }

        val uri = try {
            URI(normalized)
        } catch (exception: Exception) {
            throw IllegalArgumentException("Invalid API base URL.")
        }

        require(
            uri.scheme.equals("https", ignoreCase = true) &&
            !uri.host.isNullOrBlank()
        ) {
            "Only valid HTTPS API URLs are accepted."
        }

        require(
            uri.rawUserInfo == null &&
            uri.rawQuery == null &&
            uri.rawFragment == null
        ) {
            "Credentials, query parameters and fragments are not allowed in the base URL."
        }

        val json = Json {
            ignoreUnknownKeys = true
        }

        val httpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(15, TimeUnit.SECONDS)
            .callTimeout(20, TimeUnit.SECONDS)
            .build()

        return Retrofit.Builder()
            .baseUrl(normalized)
            .client(httpClient)
            .addConverterFactory(
                json.asConverterFactory(contentType)
            )
            .build()
            .create(MarketApi::class.java)
    }
}
