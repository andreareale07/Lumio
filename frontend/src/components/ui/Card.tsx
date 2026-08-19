import type { HTMLAttributes } from "react";

export function Card({ className = "", children, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border border-border bg-surface p-4 shadow-sm ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
