import type { PluginListenerHandle } from '@capacitor/core';

// === QoreMdns — native mDNS discovery for _qoresence._tcp ===
export interface QoreMdnsHost {
  name: string;
  host: string;
  port: number;
}
export interface DiscoverOptions {
  timeoutMs?: number;
}
export interface DiscoverResult {
  hosts: QoreMdnsHost[];
}
export interface QoreMdnsPlugin {
  discover(options: DiscoverOptions): Promise<DiscoverResult>;
}

// === QoreBackground — foreground service for background keep-alive ===
export interface StartForegroundOptions {
  url: string;
}
export interface QoreBackgroundPlugin {
  startForeground(options: StartForegroundOptions): Promise<void>;
  stopForeground(): Promise<void>;
}

// Register the plugins on the Capacitor proxy so `Capacitor.Plugins.QoreMdns`
// resolves at runtime in the WebView. These are no-op stubs on web.
import { registerPlugin } from '@capacitor/core';
export const QoreMdns = registerPlugin<QoreMdnsPlugin>('QoreMdns');
export const QoreBackground = registerPlugin<QoreBackgroundPlugin>('QoreBackground');
