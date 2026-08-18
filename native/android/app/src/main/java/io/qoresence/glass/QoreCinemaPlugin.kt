package io.qoresence.glass

import android.app.PictureInPictureParams
import android.os.Build
import android.util.Rational
import android.view.WindowManager
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import java.lang.ref.WeakReference

@CapacitorPlugin(name = "QoreCinema")
class QoreCinemaPlugin : Plugin() {

    companion object {
        @Volatile
        private var autoPip = true

        @Volatile
        private var instance: WeakReference<QoreCinemaPlugin>? = null

        @JvmStatic
        fun autoPipEnabled(): Boolean = autoPip

        @JvmStatic
        fun notifyPipChanged(active: Boolean) {
            instance?.get()?.emitPipChanged(active)
        }
    }

    override fun load() {
        super.load()
        instance = WeakReference(this)
    }

    override fun handleOnDestroy() {
        if (instance?.get() === this) {
            instance = null
        }
        super.handleOnDestroy()
    }

    fun emitPipChanged(active: Boolean) {
        val data = JSObject()
        data.put("active", active)
        notifyListeners("pipChanged", data)
    }

    @PluginMethod
    fun keepAwake(call: PluginCall) {
        val on = call.getBoolean("on", true) ?: true
        activity.runOnUiThread {
            if (on) {
                activity.window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            } else {
                activity.window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            }
            call.resolve()
        }
    }

    @PluginMethod
    fun enterPip(call: PluginCall) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            call.reject("picture-in-picture requires Android 8+")
            return
        }
        activity.runOnUiThread {
            try {
                val params = PictureInPictureParams.Builder()
                    .setAspectRatio(newRational(16, 9))
                    .build()
                val ok = activity.enterPictureInPictureMode(params)
                val out = JSObject()
                out.put("ok", ok)
                call.resolve(out)
            } catch (e: Exception) {
                call.reject("pip failed: ${e.message}")
            }
        }
    }

    @PluginMethod
    fun setAutoPip(call: PluginCall) {
        autoPip = call.getBoolean("on", true) ?: true
        val out = JSObject()
        out.put("on", autoPip)
        call.resolve(out)
    }

    @PluginMethod
    fun isPip(call: PluginCall) {
        val out = JSObject()
        out.put("active", if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            activity.isInPictureInPictureMode
        } else {
            false
        })
        call.resolve(out)
    }

    private fun newRational(w: Int, h: Int): Rational = Rational(w, h)
}
