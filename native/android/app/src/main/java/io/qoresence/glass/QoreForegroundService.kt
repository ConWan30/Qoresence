package io.qoresence.glass

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import org.json.JSONObject

class QoreForegroundService : Service() {

    companion object {
        private const val TAG = "QoreForeground"
        private const val CHANNEL_ID = "qoresence_glass_bg"
        private const val NOTIF_ID = 9001
        private const val POLL_INTERVAL_MS = 5000L
        private const val CLUTCH_THRESHOLD = 0.4
    }

    private var thread: Thread? = null
    @Volatile private var running = false
    private var lastNotifiedClimax = 0.0

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val url = intent?.getStringExtra("url") ?: ""
        val notif = buildNotification("Listening for clutch on this Wi-Fi", false)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notif)
        }

        running = false
        thread?.interrupt()
        running = true
        thread = Thread {
            while (running) {
                try {
                    pollSituation(url)
                } catch (e: Exception) {
                    Log.d(TAG, "poll error: ${e.message}")
                }
                try {
                    Thread.sleep(POLL_INTERVAL_MS)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }.also { it.start() }

        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        thread?.interrupt()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun pollSituation(baseUrl: String) {
        if (baseUrl.isEmpty()) return
        val apiUrl = baseUrl.trimEnd('/') + "/api/situation"
        val conn = (URL(apiUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 3000
            readTimeout = 3000
            requestMethod = "GET"
        }
        try {
            val code = conn.responseCode
            if (code != 200) return
            val body = BufferedReader(InputStreamReader(conn.inputStream)).use { it.readText() }
            val json = JSONObject(body)

            val coupling = json.optJSONObject("coupling") ?: return
            val climax = coupling.optDouble("climax_score", coupling.optDouble("coupling", 0.0))
            val phrase = coupling.optString("phrase", "")

            if (climax > CLUTCH_THRESHOLD && climax > lastNotifiedClimax + 0.1) {
                lastNotifiedClimax = climax
                showClutchNotification(phrase, climax)
            }
            if (phrase == "IDLE" && lastNotifiedClimax > 0) {
                lastNotifiedClimax = 0.0
            }
        } finally {
            conn.disconnect()
        }
    }

    private fun showClutchNotification(phrase: String, score: Double) {
        val mgr = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        val label = if (phrase.isBlank()) "drive" else phrase
        val notif = buildNotification(
            "Clutch · $label · ${"%.2f".format(score)}",
            true
        )
        mgr.notify(NOTIF_ID + 1, notif)
    }

    private fun buildNotification(text: String, headsUp: Boolean): Notification {
        val channel = if (headsUp) "qoresence_glass_fg" else CHANNEL_ID
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, channel)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        builder.setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle("Qoresence Glass")
            .setContentText(text)
            .setOngoing(!headsUp)
            .setColor(0xFFC6F26A.toInt())
        return builder.build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val mgr = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
            val quiet = NotificationChannel(
                CHANNEL_ID,
                "Qoresence Glass Background",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Clutch moment monitoring while app is backgrounded"
            }
            mgr.createNotificationChannel(quiet)
            val clutch = NotificationChannel(
                "qoresence_glass_fg",
                "Qoresence Clutch",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Clutch moment alerts"
                enableVibration(true)
            }
            mgr.createNotificationChannel(clutch)
        }
    }
}
