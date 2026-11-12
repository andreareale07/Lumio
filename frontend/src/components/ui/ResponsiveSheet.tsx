import type { ReactNode } from "react";

import { useIsDesktop } from "../../lib/useIsDesktop";
import { BottomSheet } from "./BottomSheet";
import { Dialog } from "./Dialog";

interface ResponsiveSheetProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** Azioni in fondo: restano fisse sia nella finestra sia nel foglio mobile. */
  footer?: ReactNode;
  size?: "md" | "lg";
}

/** Finestra su desktop, bottom sheet sotto `md`: il contenuto e' lo stesso.
 * Per i flussi che su smartphone devono restare nello schermo (mobile first). */
export function ResponsiveSheet({ open, onClose, title, children, footer, size }: ResponsiveSheetProps) {
  const isDesktop = useIsDesktop();
  if (isDesktop) {
    return (
      <Dialog open={open} onClose={onClose} title={title} footer={footer} size={size}>
        {children}
      </Dialog>
    );
  }
  return (
    <BottomSheet open={open} onClose={onClose} title={title} footer={footer}>
      {children}
    </BottomSheet>
  );
}
