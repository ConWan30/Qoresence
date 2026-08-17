package io.qoresence.glass

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.os.Build
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin

@CapacitorPlugin(name = "QoreBackground")
class QoreBackgroundPlugin : Plugin() {

    companion object {
        private const val CHANNEL_ID = "qoresence_glass_fg"
        private const val NOTIF_BASE = 9100
    }

    init {
        createChannel()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val mgr = context.getSystemService(android.content.Context.NOTIFICATION_SERVICE)
                as NotificationManager
            val ch = NotificationChannel(
                CHANNEL_ID,
                "Qoresence Clutch",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Clutch moment alerts"
                enableVibration(true)
            }
            mgr.createNotificationChannel(ch)
        }
    }

    @PluginMethod
    fun startForeground(call: PluginCall) {
        val url = call.getString("url") ?: ""
        if (url.isEmpty()) {
            call.reject("url is required")
            return
        }
        try {
            val intent = Intent(context, QoreForegroundService::class.java)
            intent.putExtra("url", url)
            context.startForegroundService(intent)
            call.resolve()
        } catch (e: Exception) {
            call.reject("Failed to start foreground service: ${e.message}")
        }
    }

    @PluginMethod
    fun stopForeground(call: PluginCall) {
        try {
            val intent = Intent(context, QoreForegroundService::class.java)
            context.stopService(intent)
        } catch (_: Exception) {
        }
        call.resolve()
    }

    @PluginMethod
    fun notify(call: PluginCall) {
        val title = call.getString("title", "Qoresence") ?: "Qoresence"
        val body = call.getString("body", "") ?: ""
        val id = call.getInt("id", (System.currentTimeMillis() % 100000).toInt())
            ?: (System.currentTimeMillis() % 100000).toInt()
        try {
            val mgr = context.getSystemService(android.content.Context.NOTIFICATION_SERVICE)
                as NotificationManager
            val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                android.app.Notification.Builder(context, CHANNEL_ID)
            } else {
                android.app.Notification.Builder(context)
            }
            val notif = builder
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentTitle(title)
                .setContentText(body)
                .setColor(0xFFC6F26A.toInt())
                .setAutoCancel(true)
                .build()
            mgr.notify(NOTIF_BASE + id, notif)
            call.resolve()
        } catch (e: Exception) {
            call.reject("notify failed: ${e.message}")
        }
    }
}

