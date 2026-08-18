import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'io.qoresence.glass',
  appName: 'Qoresence Glass',
  webDir: 'www',
  bundledWebRuntime: false,
  server: {
    // In production, bundle the PWA shell into www/ and load locally.
    // For dev, you can set androidScheme to 'http' and point hostname
    // to the PC's LAN IP. Bundled is the default — no remote URL needed.
    androidScheme: 'http',
  },
  android: {
    allowMixedContent: true,
    // Required for LAN HTTP (the deck is http://, not https://)
    captureInput: true,
  },
};

export default config;
