
package com.xauusdpro.android

import android.app.Activity
import android.os.Bundle
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.TextView
import android.content.Context
import org.json.JSONObject
import java.util.Locale

private data class MarketCandle(
    val time: String,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double
)

private data class StructureInfo(
    val detected: Boolean,
    val label: String,
    val startIndex: Int,
    val endIndex: Int,
    val upperStart: Double,
    val upperEnd: Double,
    val lowerStart: Double,
    val lowerEnd: Double
)

private data class MarketSnapshot(
    val source: String,
    val mode: String,
    val timeframe: String,
    val lastTime: String,
    val lastClose: Double,
    val candles: List<MarketCandle>,
    val structure: StructureInfo
)

class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val snapshot = loadSnapshot()

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.rgb(13, 18, 28))
            setPadding(dp(15), dp(12), dp(15), dp(12))
            layoutDirection = View.LAYOUT_DIRECTION_RTL
        }

        root.addView(
            makeText("tajik_trad", 23f, Color.WHITE),
            LinearLayout.LayoutParams(-1, dp(42))
        )

        root.addView(
            makeText(
                "نمایشگر آموزشی نمودار طلا",
                14f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(32))
        )

        val priceText = String.format(
            Locale.US,
            "آخرین قیمت ثبت‌شده: %.2f",
            snapshot.lastClose
        )

        root.addView(
            makeText(priceText, 18f, Color.WHITE),
            LinearLayout.LayoutParams(-1, dp(38))
        )

        val structureText = if (snapshot.structure.detected) {
            "نوع ساختار هندسی: ${snapshot.structure.label}"
        } else {
            "نوع ساختار هندسی: فعلاً قابل‌تشخیص نیست"
        }

        root.addView(
            makeText(structureText, 15f, Color.rgb(255, 190, 90)),
            LinearLayout.LayoutParams(-1, dp(38))
        )

        val chart = GoldChartView(
            this,
            snapshot.candles,
            snapshot.structure
        )

        root.addView(
            chart,
            LinearLayout.LayoutParams(-1, 0, 1f)
        )

        root.addView(
            makeText(
                "بازه زمانی: ${snapshot.timeframe} | حالت: تاریخی و آفلاین",
                12f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(30))
        )

        root.addView(
            makeText(
                "منبع: ${snapshot.source}",
                12f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(28))
        )

        root.addView(
            makeText(
                "آخرین رکورد: ${snapshot.lastTime}",
                11f,
                Color.LTGRAY
            ),
            LinearLayout.LayoutParams(-1, dp(28))
        )

        root.addView(
            makeText(
                "توجه: GC=F قرارداد آتی طلاست، نه قیمت نقدی دقیق XAU/USD.",
                11f,
                Color.rgb(255, 190, 90)
            ),
            LinearLayout.LayoutParams(-1, dp(38))
        )

        setContentView(root)
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
        }
    }

    private fun loadSnapshot(): MarketSnapshot {
        return try {
            val raw = assets.open("market_snapshot.json")
                .bufferedReader()
                .use { it.readText() }

            val root = JSONObject(raw)
            val array = root.getJSONArray("candles")
            val candles = mutableListOf<MarketCandle>()

            for (i in 0 until array.length()) {
                val item = array.getJSONObject(i)

                candles.add(
                    MarketCandle(
                        item.optString("time"),
                        item.optDouble("open"),
                        item.optDouble("high"),
                        item.optDouble("low"),
                        item.optDouble("close")
                    )
                )
            }

            val s = root.optJSONObject("structure") ?: JSONObject()

            val structure = StructureInfo(
                detected = s.optBoolean("detected", false),
                label = s.optString(
                    "label",
                    "ساختار هندسی قابل‌تشخیص نیست"
                ),
                startIndex = s.optInt("start_index", 0),
                endIndex = s.optInt("end_index", 0),
                upperStart = s.optDouble("upper_start", 0.0),
                upperEnd = s.optDouble("upper_end", 0.0),
                lowerStart = s.optDouble("lower_start", 0.0),
                lowerEnd = s.optDouble("lower_end", 0.0)
            )

            MarketSnapshot(
                source = root.optString("source"),
                mode = root.optString("mode"),
                timeframe = root.optString("timeframe"),
                lastTime = root.optString("lastTime"),
                lastClose = root.optDouble("lastClose"),
                candles = candles,
                structure = structure
            )

        } catch (e: Exception) {
            MarketSnapshot(
                source = "داده در دسترس نیست",
                mode = "ERROR",
                timeframe = "5m",
                lastTime = "-",
                lastClose = 0.0,
                candles = emptyList(),
                structure = StructureInfo(
                    false,
                    "خطا در خواندن داده",
                    0, 0, 0.0, 0.0, 0.0, 0.0
                )
            )
        }
    }
}

private class GoldChartView(
    context: Context,
    private val candles: List<MarketCandle>,
    private val structure: StructureInfo
) : View(context) {

    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        canvas.drawColor(Color.rgb(13, 18, 28))

        if (candles.isEmpty()) {
            paint.color = Color.WHITE
            paint.textSize = 36f
            canvas.drawText(
                "داده‌ای برای نمایش وجود ندارد",
                30f,
                height / 2f,
                paint
            )
            return
        }

        val left = 78f
        val right = width - 18f
        val top = 35f
        val bottom = height - 48f

        val plotWidth = right - left
        val plotHeight = bottom - top

        if (plotWidth <= 0f || plotHeight <= 0f) return

        val minPrice = candles.minOf { it.low }
        val maxPrice = candles.maxOf { it.high }

        val priceRange = (maxPrice - minPrice).coerceAtLeast(0.01)

        fun y(price: Double): Float {
            return bottom -
                (((price - minPrice) / priceRange).toFloat() * plotHeight)
        }

        fun x(index: Int): Float {
            val step = plotWidth / candles.size
            return left + (index + 0.5f) * step
        }

        // Grid and price labels
        paint.color = Color.rgb(48, 57, 72)
        paint.strokeWidth = 1f
        paint.style = Paint.Style.STROKE

        paint.textSize = 22f
        paint.textAlign = Paint.Align.RIGHT

        for (i in 0..4) {
            val price = maxPrice - (priceRange * i / 4.0)
            val yy = y(price)

            canvas.drawLine(left, yy, right, yy, paint)

            paint.style = Paint.Style.FILL
            paint.color = Color.LTGRAY

            canvas.drawText(
                String.format(Locale.US, "%.2f", price),
                left - 7f,
                yy + 7f,
                paint
            )

            paint.style = Paint.Style.STROKE
            paint.color = Color.rgb(48, 57, 72)
        }

        // Historical candlesticks
        val step = plotWidth / candles.size
        val bodyWidth = (step * 0.65f).coerceAtLeast(2f)

        for ((index, candle) in candles.withIndex()) {
            val centerX = x(index)

            val rising = candle.close >= candle.open

            val candleColor = if (rising) {
                Color.rgb(60, 190, 145)
            } else {
                Color.rgb(225, 91, 91)
            }

            paint.color = candleColor
            paint.strokeWidth = 2f
            paint.style = Paint.Style.STROKE

            canvas.drawLine(
                centerX,
                y(candle.high),
                centerX,
                y(candle.low),
                paint
            )

            val bodyTop = y(maxOf(candle.open, candle.close))
            val bodyBottom = y(minOf(candle.open, candle.close))

            paint.style = Paint.Style.FILL

            val rect = RectF(
                centerX - bodyWidth / 2f,
                bodyTop,
                centerX + bodyWidth / 2f,
                maxOf(bodyTop + 2f, bodyBottom)
            )

            canvas.drawRect(rect, paint)
        }

        // Geometry-only structure overlay
        if (structure.detected) {
            val start = structure.startIndex.coerceIn(0, candles.size - 1)
            val end = structure.endIndex.coerceIn(0, candles.size - 1)

            if (end > start) {
                paint.color = Color.rgb(255, 190, 70)
                paint.strokeWidth = 3f
                paint.style = Paint.Style.STROKE

                canvas.drawLine(
                    x(start),
                    y(structure.upperStart),
                    x(end),
                    y(structure.upperEnd),
                    paint
                )

                paint.color = Color.rgb(90, 180, 255)

                canvas.drawLine(
                    x(start),
                    y(structure.lowerStart),
                    x(end),
                    y(structure.lowerEnd),
                    paint
                )
            }
        }

        // Time labels
        paint.style = Paint.Style.FILL
        paint.color = Color.LTGRAY
        paint.textSize = 20f
        paint.textAlign = Paint.Align.LEFT

        canvas.drawText(
            candles.first().time.take(16),
            left,
            height - 12f,
            paint
        )

        paint.textAlign = Paint.Align.RIGHT

        canvas.drawText(
            candles.last().time.take(16),
            right,
            height - 12f,
            paint
        )
    }
}
