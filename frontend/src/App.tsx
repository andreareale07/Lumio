import { BrowserRouter } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { AppRouter } from "./app/router/AppRouter";
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
  return (
    <ThemeProvider>
      <QueryProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRouter key={i18n.language} />
          </AuthProvider>
        </BrowserRouter>
      </QueryProvider>
    </ThemeProvider>
  );
}

export default App;
