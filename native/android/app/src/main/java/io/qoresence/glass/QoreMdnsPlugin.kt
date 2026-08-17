package io.qoresence.glass

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import com.getcapacitor.JSArray
import com.getcapacitor.JSObject
import com.getcapacitor.Plugin
import com.getcapacitor.PluginCall
import com.getcapacitor.PluginMethod
import com.getcapacitor.annotation.CapacitorPlugin
import java.util.concurrent.TimeUnit

@CapacitorPlugin(name = "QoreMdns")
class QoreMdnsPlugin : Plugin() {

    @PluginMethod
    fun discover(call: PluginCall) {
        val timeoutMs = call.getInt("timeoutMs", 3000) ?: 3000
        val nsdManager =
            context.getSystemService(Context.NSD_SERVICE) as? NsdManager
        if (nsdManager == null) {
            call.resolve(JSObject().put("hosts", JSArray()))
            return
        }

        val hosts = mutableListOf<JSObject>()
        val lock = Object()
        var discoveryListener: NsdManager.DiscoveryListener? = null

        val resolveLatch = java.util.concurrent.CountDownLatch(1)
        var pendingCount = 0

        discoveryListener = object : NsdManager.DiscoveryListener {
            override fun onStartDiscoveryFailed(serviceType: String?, errorCode: Int) {
                synchronized(lock) { resolveLatch.countDown() }
            }

            override fun onStopDiscoveryFailed(serviceType: String?, errorCode: Int) {}

            override fun onDiscoveryStarted(serviceType: String?) {}

            override fun onDiscoveryStopped(serviceType: String?) {}

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                if (!serviceInfo.serviceType.contains("_qoresence._tcp")) return
                synchronized(lock) { pendingCount++ }
                // Resolve to get host + port
                val resolveListener = object : NsdManager.ResolveListener {
                    override fun onServiceResolved(info: NsdServiceInfo) {
                        val host = info.host?.hostAddress ?: ""
                        val port = info.port
                        val name = info.serviceName
                        if (host.isNotEmpty()) {
                            val obj = JSObject()
                            obj.put("name", name)
                            obj.put("host", host)
                            obj.put("port", port)
                            synchronized(lock) {
                                hosts.add(obj)
                                pendingCount--
                                if (pendingCount <= 0) resolveLatch.countDown()
                            }
                        } else {
                            synchronized(lock) {
                                pendingCount--
                                if (pendingCount <= 0) resolveLatch.countDown()
                            }
                        }
                    }

                    override fun onResolveFailed(info: NsdServiceInfo, errorCode: Int) {
                        synchronized(lock) {
                            pendingCount--
                            if (pendingCount <= 0) resolveLatch.countDown()
                        }
                    }
                }
                try {
                    nsdManager.resolveService(serviceInfo, resolveListener)
                } catch (e: Exception) {
                    synchronized(lock) {
                        pendingCount--
                        if (pendingCount <= 0) resolveLatch.countDown()
                    }
                }
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo?) {}
        }

        try {
            nsdManager.discoverServices("_qoresence._tcp.", NsdManager.PROTOCOL_DNS_SD, discoveryListener)
        } catch (e: Exception) {
            call.resolve(JSObject().put("hosts", JSArray()))
            return
        }

        // Wait for discovery + resolution or timeout
        try {
            resolveLatch.await(timeoutMs.toLong(), TimeUnit.MILLISECONDS)
        } catch (_: InterruptedException) {
        }

        // Stop discovery
        try {
            nsdManager.stopServiceDiscovery(discoveryListener)
        } catch (_: Exception) {
        }

        // Give a brief moment for any in-flight resolves
        Thread.sleep(200)

        val arr = JSArray()
        synchronized(lock) {
            for (h in hosts) arr.put(h)
        }
        val result = JSObject()
        result.put("hosts", arr)
        call.resolve(result)
    }
}
