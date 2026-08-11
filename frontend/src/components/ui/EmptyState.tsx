import type { ComponentType, ReactNode } from "react";

interface EmptyStateProps {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: ReactNode;
}

/** SPEC_FE §55: ogni sezione deve avere un empty state progettato, non un
 * elenco/grafico vuoto senza spiegazione. */
export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border p-10 text-center">
      {Icon && <Icon className="h-8 w-8 text-text-muted" />}
      <p className="font-medium text-text">{title}</p>
      {description && <p className="text-sm text-text-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
