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
export interface NotifyOptions {
  title?: string;
  body?: string;
  id?: number;
}
export interface QoreBackgroundPlugin {
  requestNotify(): Promise<void>;
  startForeground(options: StartForegroundOptions): Promise<void>;
  stopForeground(): Promise<void>;
  notify(options: NotifyOptions): Promise<void>;
}

// === QoreCinema — keep-awake + picture-in-picture ===
export interface KeepAwakeOptions {
  on?: boolean;
}
export interface AutoPipOptions {
  on?: boolean;
}
export interface QoreCinemaPlugin {
  keepAwake(options: KeepAwakeOptions): Promise<void>;
  enterPip(): Promise<{ ok: boolean }>;
  setAutoPip(options: AutoPipOptions): Promise<{ on: boolean }>;
  isPip(): Promise<{ active: boolean }>;
  addListener(
    eventName: 'pipChanged',
    listenerFunc: (event: { active: boolean }) => void,
  ): Promise<{ remove: () => Promise<void> }>;
}

import { registerPlugin } from '@capacitor/core';
export const QoreMdns = registerPlugin<QoreMdnsPlugin>('QoreMdns');
export const QoreBackground = registerPlugin<QoreBackgroundPlugin>('QoreBackground');
export const QoreCinema = registerPlugin<QoreCinemaPlugin>('QoreCinema');
