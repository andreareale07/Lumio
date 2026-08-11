import { LogOut, Monitor, Moon, Sun } from "lucide-react";

import { useAuth } from "../../app/providers/AuthProvider";
import { useTheme } from "../../app/providers/ThemeProvider";

const THEME_ICONS = { light: Sun, dark: Moon, system: Monitor } as const;

export function Topbar() {
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const ThemeIcon = THEME_ICONS[theme];

  const cycleTheme = () => {
    const order = ["system", "light", "dark"] as const;
    const next = order[(order.indexOf(theme) + 1) % order.length];
    setTheme(next);
  };

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-surface px-4">
      <span className="font-semibold text-text">Lumio</span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={cycleTheme}
          aria-label={`Tema: ${theme}`}
          title={`Tema: ${theme}`}
          className="rounded-md p-2 text-text-muted hover:bg-surface-hover hover:text-text"
        >
          <ThemeIcon className="h-4 w-4" />
        </button>
        {user && <span className="hidden text-sm text-text-muted sm:inline">{user.display_name}</span>}
        <button
          type="button"
          onClick={() => void logout()}
          aria-label="Esci"
          title="Esci"
          className="rounded-md p-2 text-text-muted hover:bg-surface-hover hover:text-text"
        >
          <LogOut className="h-4 w-4" />
        </button>
      </div>
    </header>
  );
}
