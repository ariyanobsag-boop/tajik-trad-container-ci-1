package com.xauusdpro.android

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView

import com.xauusdpro.android.data.IntradayPricePoint
import com.xauusdpro.android.data.IntradayFeedResponse
import com.xauusdpro.android.data.SpotFeedResponse
import com.xauusdpro.android.data.MarketApi
import com.xauusdpro.android.data.MarketApiFactory

import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull

import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

import java.util.Locale

class MainActivity : Activity() {

    companion object {
        private const val SPOT_INTERVAL_MS = 3_000L
        private const val INTRADAY_INTERVAL_MS = 5_000L
        private const val MAX_CHART_POINTS = 900
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private var api: MarketApi? = null
    private var isActive = false

    private var spotCall: Call<SpotFeedResponse>? = null
    private var intradayCall: Call<IntradayFeedResponse>? = null

    private var spotInFlight = false
    private var intradayInFlight = false
    private var hasSpotPrice = false

    private lateinit var priceText: TextView
    private lateinit var connectionText: TextView
    private lateinit var sourceText: TextView
    private lateinit var freshnessText: TextView
    private lateinit var intradayText: TextView
    private lateinit var chartInfoText: TextView
    private lateinit var chart: LivePriceChartView

    private val spotPoll = object : Runnable {
        override fun run() {
            if (!isActive) return
            requestSpot()
            mainHandler.postDelayed(this, SPOT_INTERVAL_MS)
        }
    }

    private val intradayPoll = object : Runnable {
        override fun run() {
            if (!isActive) return
            requestIntraday()
            mainHandler.postDelayed(this, INTRADAY_INTERVAL_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        buildScreen()
        configureApi()
    }

    private fun buildScreen() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(13, 18, 28))
            setPadding(dp(15), dp(12), dp(15), dp(10))
            layoutDirection = View.LAYOUT_DIRECTION_RTL
        }

        root.addView(
            makeText("VORTEXTRAD", 25f, Color.WHITE),
            LinearLayout.LayoutParams(-1, dp(42))
        )

        root.addView(
            makeText(
                "نمایشگر آموزشی و زنده اطلاعات طلا",
                14f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(30))
        )

        priceText = makeText(
            "در انتظار دریافت قیمت...",
            24f,
            Color.WHITE
        ).apply {
            gravity = Gravity.CENTER
            textDirection = View.TEXT_DIRECTION_LTR
        }

        root.addView(
            priceText,
            LinearLayout.LayoutParams(-1, dp(62))
        )

        connectionText = makeText(
            "وضعیت اتصال: در انتظار اتصال",
            12f,
            Color.LTGRAY
        )
        root.addView(
            connectionText,
            LinearLayout.LayoutParams(-1, dp(28))
        )

        sourceText = makeText(
            "منبع داده: هنوز دریافت نشده",
            11f,
            Color.LTGRAY
        )
        root.addView(
            sourceText,
            LinearLayout.LayoutParams(-1, dp(27))
        )

        freshnessText = makeText(
            "تازگی اطلاعات: نامشخص",
            11f,
            Color.rgb(255, 190, 90)
        )
        root.addView(
            freshnessText,
            LinearLayout.LayoutParams(-1, dp(28))
        )

        root.addView(
            makeText(
                "نمودار قیمت دریافتی از منبع",
                15f,
                Color.WHITE
            ),
            LinearLayout.LayoutParams(-1, dp(34))
        )

        chartInfoText = makeText(
            "نمودار نقطه‌ای، بدون ساخت کندل مصنوعی",
            11f,
            Color.LTGRAY
        )
        root.addView(
            chartInfoText,
            LinearLayout.LayoutParams(-1, dp(25))
        )

        chart = LivePriceChartView(this)
        root.addView(
            chart,
            LinearLayout.LayoutParams(-1, 0, 1f)
        )

        intradayText = makeText(
            "اطلاعات نمودار: در انتظار دریافت",
            11f,
            Color.LTGRAY
        )
        root.addView(
            intradayText,
            LinearLayout.LayoutParams(-1, dp(30))
        )

        root.addView(
            makeText(
                "دوره دریافت قیمت: ۳ ثانیه | نمودار: ۵ ثانیه",
                11f,
                Color.rgb(100, 190, 255)
            ),
            LinearLayout.LayoutParams(-1, dp(29))
        )

        root.addView(
            makeText(
                "این برنامه فقط داده و نمودار مرجع را نمایش می‌دهد.",
                10f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(25))
        )

        setContentView(root)
    }

    private fun configureApi() {
        val baseUrl = BuildConfig.API_BASE_URL.trim()

        if (baseUrl.isEmpty()) {
            connectionText.text =
                "سرور HTTPS برنامه هنوز تنظیم نشده است."
            priceText.text = "قیمت زنده در دسترس نیست"
            freshnessText.text =
                "پس از تنظیم آدرس سرور، دریافت داده شروع می‌شود."
            return
        }

        try {
            api = MarketApiFactory.create(baseUrl)
            connectionText.text =
                "آدرس سرور تنظیم شد؛ آماده دریافت اطلاعات."
        } catch (e: Exception) {
            api = null
            connectionText.text =
                "خطا در تنظیم آدرس سرور: ${e.message ?: "آدرس نامعتبر"}"
        }
    }

    override fun onResume() {
        super.onResume()

        if (api == null) return

        isActive = true

        mainHandler.removeCallbacks(spotPoll)
        mainHandler.removeCallbacks(intradayPoll)

        mainHandler.post(spotPoll)
        mainHandler.post(intradayPoll)
    }

    override fun onPause() {
        isActive = false

        mainHandler.removeCallbacks(spotPoll)
        mainHandler.removeCallbacks(intradayPoll)

        spotCall?.cancel()
        intradayCall?.cancel()

        spotCall = null
        intradayCall = null

        spotInFlight = false
        intradayInFlight = false

        super.onPause()
    }

    private fun requestSpot() {
        val currentApi = api ?: return
        if (spotInFlight) return

        val call = currentApi.getSpot()

        spotInFlight = true
        spotCall = call

        call.enqueue(object : Callback<SpotFeedResponse> {

            override fun onResponse(
                call: Call<SpotFeedResponse>,
                response: Response<SpotFeedResponse>
            ) {
                if (!isActive || spotCall !== call) return

                spotCall = null
                spotInFlight = false

                if (response.isSuccessful) {
                    val data = response.body()

                    if (data != null) {
                        showSpot(data)
                    } else {
                        connectionText.text =
                            "سرور پاسخ خالی ارسال کرد."
                    }
                } else {
                    connectionText.text =
                        "خطای دریافت قیمت از سرور: HTTP ${response.code()}"
                }
            }

            override fun onFailure(
                call: Call<SpotFeedResponse>,
                error: Throwable
            ) {
                if (!isActive || spotCall !== call) return

                spotCall = null
                spotInFlight = false

                connectionText.text =
                    "دریافت قیمت ناموفق بود؛ اتصال دوباره بررسی می‌شود."

                if (!hasSpotPrice) {
                    priceText.text = "قیمت هنوز دریافت نشده"
                }
            }
        })
    }

    private fun requestIntraday() {
        val currentApi = api ?: return
        if (intradayInFlight) return

        val call = currentApi.getIntraday(6)

        intradayInFlight = true
        intradayCall = call

        call.enqueue(object : Callback<IntradayFeedResponse> {

            override fun onResponse(
                call: Call<IntradayFeedResponse>,
                response: Response<IntradayFeedResponse>
            ) {
                if (!isActive || intradayCall !== call) return

                intradayCall = null
                intradayInFlight = false

                if (response.isSuccessful) {
                    val data = response.body()

                    if (data != null) {
                        showIntraday(data)
                    } else {
                        intradayText.text =
                            "پاسخ نمودار خالی است."
                    }
                } else {
                    intradayText.text =
                        "خطای نمودار: HTTP ${response.code()}"
                }
            }

            override fun onFailure(
                call: Call<IntradayFeedResponse>,
                error: Throwable
            ) {
                if (!isActive || intradayCall !== call) return

                intradayCall = null
                intradayInFlight = false

                intradayText.text =
                    "دریافت جدید نمودار ناموفق بود؛ آخرین داده نمایش داده می‌شود."
            }
        })
    }

    private fun showSpot(data: SpotFeedResponse) {
        hasSpotPrice = true

        priceText.text = String.format(
            Locale.US,
            "%.2f USD / oz",
            data.priceUsdPerTroyOunce
        )

        connectionText.text =
            "پاسخ سرور دریافت شد | وضعیت منبع: ${data.providerStatus}"

        val provider = sourceName(data.providerSource, data.provider)

        val timestamp = data.sourceTimestamp
            ?: data.providerReceivedAt
            ?: data.receivedAt

        sourceText.text =
            "منبع: $provider | زمان داده: $timestamp"

        val freshness = friendlyFreshness(data.freshnessStatus)
        val staleWarning = if (data.staleFlag) {
            " | داده قدیمی است"
        } else {
            ""
        }

        freshnessText.text =
            "تازگی: $freshness | عمر منبع: ${seconds(data.sourceAgeSeconds)} ثانیه | کش سرور: ${seconds(data.serverCacheAgeSeconds)} ثانیه$staleWarning"

        freshnessText.setTextColor(
            if (data.staleFlag) Color.rgb(255, 150, 90)
            else Color.rgb(120, 210, 160)
        )
    }

    private fun showIntraday(data: IntradayFeedResponse) {
        chart.setPoints(data.points)

        chartInfoText.text =
            "نمودار ${data.instrument} | ${data.points.size} نقطه واقعی"

        val timestamp = data.latestSourceTimestamp
            ?: data.providerReceivedAt
            ?: data.receivedAt

        val orderWarning = if (data.sourceOrderValid) {
            ""
        } else {
            " | ترتیب زمانی نیازمند بررسی"
        }

        val staleLabel = friendlyFreshness(data.freshnessStatus)

        intradayText.text =
            "تعداد نقاط: ${data.pointCount} | آخرین زمان منبع: $timestamp | تازگی: $staleLabel$orderWarning"
    }

    private fun sourceName(
        value: JsonElement?,
        fallback: String
    ): String {
        if (value == null || value == JsonNull) return fallback

        return value.toString()
            .trim('"')
            .ifBlank { fallback }
            .take(100)
    }

    private fun friendlyFreshness(value: String): String {
        val normalized = value.lowercase(Locale.US)

        return when {
            normalized.contains("fresh") -> "تازه"
            normalized.contains("stale") -> "قدیمی"
            normalized.contains("unknown") -> "نامشخص"
            else -> value.take(40)
        }
    }

    private fun seconds(value: Double?): String {
        if (value == null) return "-"

        return String.format(Locale.US, "%.1f", value)
    }

    private fun dp(value: Int): Int {
        return (value * resources.displayMetrics.density).toInt()
    }

    private fun makeText(
        value: String,
        size: Float,
        color: Int
    ): TextView {
        return TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            gravity = Gravity.CENTER_VERTICAL or Gravity.RIGHT
            textDirection = View.TEXT_DIRECTION_RTL
            setPadding(dp(5), 0, dp(5), 0)
            maxLines = 2
        }
    }

    private class LivePriceChartView(
        context: android.content.Context
    ) : View(context) {

        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        private var points: List<IntradayPricePoint> = emptyList()

        fun setPoints(value: List<IntradayPricePoint>) {
            points = value
                .sortedBy { it.epochSeconds }
                .takeLast(MAX_CHART_POINTS)

            invalidate()
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)

            canvas.drawColor(Color.rgb(13, 18, 28))

            if (points.isEmpty()) {
                paint.color = Color.LTGRAY
                paint.textSize = 30f
                paint.textAlign = Paint.Align.CENTER

                canvas.drawText(
                    "در انتظار دریافت نقاط نمودار...",
                    width / 2f,
                    height / 2f,
                    paint
                )
                return
            }

            val density = resources.displayMetrics.density
            val left = 100f * density
            val right = width - 18f * density
            val top = 22f * density
            val bottom = height - 48f * density

            if (right <= left || bottom <= top) return

            val minPrice = points.minOf { it.p }
            val maxPrice = points.maxOf { it.p }

            val originalRange = maxPrice - minPrice
            val padding = if (originalRange > 0.0) {
                originalRange * 0.08
            } else {
                maxOf(maxPrice * 0.001, 0.5)
            }

            val low = minPrice - padding
            val high = maxPrice + padding
            val priceRange = (high - low).coerceAtLeast(0.01)

            val firstTime = points.first().epochSeconds
            val lastTime = points.last().epochSeconds
            val timeRange = (lastTime - firstTime).coerceAtLeast(1L)

            fun x(index: Int): Float {
                if (points.size == 1) {
                    return (left + right) / 2f
                }

                val ratio =
                    (points[index].epochSeconds - firstTime).toFloat() /
                    timeRange.toFloat()

                return left + ratio * (right - left)
            }

            fun y(price: Double): Float {
                val ratio = ((price - low) / priceRange).toFloat()
                return bottom - ratio * (bottom - top)
            }

            // Horizontal price grid.
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 1f * density
            paint.color = Color.rgb(48, 57, 72)
            paint.textSize = 11f * density
            paint.textAlign = Paint.Align.RIGHT

            for (i in 0..4) {
                val price = high - (priceRange * i / 4.0)
                val yy = y(price)

                canvas.drawLine(left, yy, right, yy, paint)

                paint.style = Paint.Style.FILL
                paint.color = Color.LTGRAY

                canvas.drawText(
                    String.format(Locale.US, "%.2f", price),
                    left - 8f * density,
                    yy + 4f * density,
                    paint
                )

                paint.style = Paint.Style.STROKE
                paint.color = Color.rgb(48, 57, 72)
            }

            // Actual source price points, joined as a line.
            val path = Path()

            for ((index, point) in points.withIndex()) {
                val px = x(index)
                val py = y(point.p)

                if (index == 0) {
                    path.moveTo(px, py)
                } else {
                    path.lineTo(px, py)
                }
            }

            paint.color = Color.rgb(65, 190, 220)
            paint.strokeWidth = 2.5f * density
            paint.style = Paint.Style.STROKE
            paint.strokeCap = Paint.Cap.ROUND
            paint.strokeJoin = Paint.Join.ROUND

            canvas.drawPath(path, paint)

            // Last received point.
            val latest = points.last()
            val lastX = x(points.lastIndex)
            val lastY = y(latest.p)

            paint.style = Paint.Style.FILL
            paint.color = Color.rgb(255, 190, 80)

            canvas.drawCircle(
                lastX,
                lastY,
                5f * density,
                paint
            )

            // Time range labels.
            paint.color = Color.LTGRAY
            paint.textSize = 10f * density
            paint.textAlign = Paint.Align.LEFT

            canvas.drawText(
                points.first().t.take(16),
                left,
                height - 10f * density,
                paint
            )

            paint.textAlign = Paint.Align.RIGHT

            canvas.drawText(
                latest.t.take(16),
                right,
                height - 10f * density,
                paint
            )
        }
    }
}
