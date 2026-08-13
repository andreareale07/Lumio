import { forwardRef } from "react";
import type { ButtonHTMLAttributes } from "react";

import { Loader2 } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "link";
export type ButtonSize = "sm" | "md" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

// Esportate cosi' che `LinkButton` (un `<Link>` di react-router-dom con lo
// stesso aspetto) possa riusarle senza duplicare le regole di stile.
export const buttonVariantClasses: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-contrast hover:bg-primary-hover",
  secondary: "bg-surface text-text border border-border hover:bg-surface-hover",
  ghost: "bg-transparent text-text hover:bg-surface-hover",
  danger: "bg-danger text-white hover:opacity-90",
  link: "bg-transparent text-primary underline-offset-2 hover:underline h-auto p-0",
};

export const buttonSizeClasses: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-sm gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  icon: "h-8 w-8 p-0",
};

// La variante "link" fissa la propria altezza/padding (h-auto p-0): le
// classi di `size` andrebbero in conflitto sulle stesse proprieta', e
// Tailwind risolve i duplicati per ordine nel foglio generato, non per
// ordine nella stringa `className` — quindi non si puo' contare su
// "appare dopo" per farla vincere. Si omettono del tutto le classi di
// size quando la variante e' "link".
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", loading = false, disabled, className = "", children, ...rest }, ref) => {
    const sizeClasses = variant === "link" ? "" : buttonSizeClasses[size];
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={`inline-flex items-center justify-center whitespace-nowrap rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${buttonVariantClasses[variant]} ${sizeClasses} ${className}`}
        {...rest}
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";
