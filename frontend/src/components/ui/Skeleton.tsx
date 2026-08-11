/** Skeleton generico (SPEC_FE §54: preferire skeleton a spinner, deve
 * rispecchiare la struttura reale del contenuto — i chiamanti compongono
 * righe/blocchi di questa forma nella shape della UI reale). */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-surface-hover ${className}`} />;
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
