import { BrowserRouter } from "react-router-dom";

import { AppRouter } from "./app/router/AppRouter";
import { AuthProvider } from "./app/providers/AuthProvider";
import { QueryProvider } from "./app/providers/QueryProvider";
import { ThemeProvider } from "./app/providers/ThemeProvider";

function App() {
  return (
    <ThemeProvider>
      <QueryProvider>
        <BrowserRouter>
          <AuthProvider>
            <AppRouter />
          </AuthProvider>
        </BrowserRouter>
      </QueryProvider>
    </ThemeProvider>
  );
}

export default App;
