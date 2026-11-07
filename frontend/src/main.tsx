import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./app/i18n";
import { loadAppLockPrefs } from "./lib/appLockPrefs";
import { initPushNavigation } from "./lib/push";
import { loadServerConfig } from "./lib/serverConfig";
import "./styles/global.css";

// Nell'app nativa server e preferenze di blocco stanno in Preferences (async):
// vanno letti prima del primo render. Sul web le due funzioni non fanno nulla.
async function bootstrap() {
  await Promise.all([loadServerConfig(), loadAppLockPrefs()]).catch(() => undefined);
  initPushNavigation();
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
}

void bootstrap();
