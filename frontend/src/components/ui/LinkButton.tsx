import type { ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { buttonSizeClasses, buttonVariantClasses, type ButtonSize, type ButtonVariant } from "./Button";

interface LinkButtonProps extends LinkProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
}

/** Stesso aspetto di `Button`, ma renderizza un `<Link>` di react-router
 * (navigazione reale, non un click handler) — per le Quick Actions
 * (SPEC_FE §19) e ogni altro punto in cui un'azione e' in realta' un link. */
export function LinkButton({ variant = "primary", size = "md", className = "", children, ...rest }: LinkButtonProps) {
  return (
    <Link
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors ${buttonVariantClasses[variant]} ${buttonSizeClasses[size]} ${className}`}
      {...rest}
    >
      {children}
    </Link>
  );
}
