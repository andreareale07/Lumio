import { useState } from "react";
import { BrowserRouter } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AppRouter } from "./app/router/AppRouter";
import { UpdateBanner } from "./components/layout/UpdateBanner";
import { AppLockProvider } from "./features/native/AppLockProvider";
import { ServerSetupScreen } from "./features/native/ServerSetupScreen";
import { useAmountsHidden } from "./lib/privacy";
import { isNativeApp } from "./lib/platform";
import { needsServerSetup } from "./lib/serverConfig";
import { AuthProvider } from "./app/providers/AuthProvider";
import { QueryProvider } from "./app/providers/QueryProvider";
import { ThemeProvider } from "./app/providers/ThemeProvider";

function App() {
  // `i18n.language` come key SOLO su AppRouter (non su AuthProvider/
  // QueryProvider, che devono restare montati: cambiare lingua non deve
  // ripetere login/refetch, SPEC_FE_REDESIGN §38): forza il remount delle
  // pagine cosi' ogni testo tradotto E ogni valore formattato via
  // `lib/format.ts` (che legge `i18n.language` fuori da React, non tramite
  // hook) si aggiorna subito — senza doverla far passare come prop/hook in
  // ogni singolo componente (fase di fondamenta: non ogni pagina e' ancora
  // migrata).
  const { i18n } = useTranslation();
  // Stesso meccanismo per la modalita' privacy (importi nascosti, `lib/privacy.ts`).
  const amountsHidden = useAmountsHidden();
  // App nativa: finche' non si e' scelto il server non c'e' nessuna API da chiamare.
  const [serverReady, setServerReady] = useState(() => !needsServerSetup());
  if (!serverReady) {
    return (
      <ThemeProvider>
        <ServerSetupScreen onSaved={() => setServerReady(true)} />
      </ThemeProvider>
    );
  }
  return (
    <ThemeProvider>
      <QueryProvider>
        <AppLockProvider>
          <BrowserRouter>
            <AuthProvider>
              <AppRouter key={`${i18n.language}-${amountsHidden}`} />
            </AuthProvider>
            {/* Nell'app nativa gli asset sono nell'APK: niente service worker. */}
            {!isNativeApp() && <UpdateBanner />}
          </BrowserRouter>
        </AppLockProvider>
      </QueryProvider>
    </ThemeProvider>
  );
}

export default App;
