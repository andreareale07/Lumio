import type { CapacitorConfig } from "@capacitor/cli";

// Guscio nativo: gli asset (`dist/`) stanno nell'APK; il server Lumio lo sceglie
// l'utente nell'app. Il nome mostrato sul telefono segue VITE_APP_NAME.
const config: CapacitorConfig = {
  appId: "app.lumio.mobile",
  appName: process.env.VITE_APP_NAME || "Lumio",
  webDir: "dist",
  server: {
    // Origin del WebView `http://localhost`: permette sia server https:// sia
    // http:// in LAN (con https non si potrebbe chiamare un server http, "mixed
    // content"). Il backend ammette questa origin in MOBILE_APP_ORIGINS.
    androidScheme: "http",
    cleartext: true,
  },
  plugins: {
    SplashScreen: { launchShowDuration: 0, backgroundColor: "#4F46E5" },
  },
};

export default config;
