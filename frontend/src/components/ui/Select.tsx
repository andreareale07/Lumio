import { forwardRef } from "react";
import type { SelectHTMLAttributes } from "react";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
}

let idCounter = 0;

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, id, className = "", children, ...rest }, ref) => {
    const selectId = id ?? `select-${++idCounter}`;
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={selectId} className="text-sm font-medium text-text">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          aria-invalid={!!error}
          className={`h-10 rounded-lg border bg-surface px-3 text-sm text-text disabled:opacity-50 ${
            error ? "border-danger" : "border-border"
          } ${className}`}
          {...rest}
        >
          {children}
        </select>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    );
  },
);
Select.displayName = "Select";
