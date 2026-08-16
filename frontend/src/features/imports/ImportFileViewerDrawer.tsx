import { useEffect, useState } from "react";
import { FileText } from "lucide-react";

import { Drawer } from "../../components/ui/Drawer";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { SkeletonRows } from "../../components/ui/Skeleton";
import type { ImportRecord } from "../../types/api";
import { fetchImportFileBlob, useImportFileContent } from "./api";

interface ImportFileViewerDrawerProps {
  importRecord: ImportRecord | null;
  onClose: () => void;
}

export function ImportFileViewerDrawer({ importRecord, onClose }: ImportFileViewerDrawerProps) {
  return (
    <Drawer
      open={!!importRecord}
      onClose={onClose}
      title={importRecord ? `File originale — ${importRecord.filename}` : "File originale"}
      widthClassName="max-w-3xl"
    >
      {importRecord?.file_type === "pdf" && <PdfFileView importId={importRecord.id} />}
      {importRecord?.file_type === "csv" && <CsvFileView importId={importRecord.id} />}
    </Drawer>
  );
}

function PdfFileView({ importId }: { importId: string }) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let url: string | null = null;
    setError(false);
    setBlobUrl(null);
    fetchImportFileBlob(importId)
      .then((blob) => {
        url = URL.createObjectURL(blob);
        setBlobUrl(url);
      })
      .catch(() => setError(true));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [importId]);

  if (error) {
    return <ErrorState message="Non siamo riusciti a caricare il file originale." />;
  }
  if (!blobUrl) {
    return <SkeletonRows rows={6} />;
  }
  return (
    <embed
      src={blobUrl}
      type="application/pdf"
      className="h-full min-h-[70vh] w-full rounded-lg border border-border"
    />
  );
}

function CsvFileView({ importId }: { importId: string }) {
  const { data, isLoading, isError, refetch } = useImportFileContent(importId);

  if (isLoading) return <SkeletonRows rows={8} />;
  if (isError || !data) {
    return <ErrorState message="Non siamo riusciti a caricare il file originale." onRetry={() => void refetch()} />;
  }
  if (data.rows.length === 0) {
    return <EmptyState icon={FileText} title="File vuoto" description="Il file originale non contiene righe di dati." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            {data.columns.map((col, i) => (
              <th key={`${col}-${i}`} className="px-2 py-1 text-left text-text-muted">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {row.map((cell, j) => (
                <td key={j} className="px-2 py-1 text-text">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.truncated && (
        <p className="mt-2 text-xs text-text-muted">
          Mostrate le prime {data.rows.length} righe su {data.total_rows} totali.
        </p>
      )}
    </div>
  );
}
