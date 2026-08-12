import { useCallback, useState } from "react";

import { Button } from "../../../components/ui/Button";
import { fetchGooglePickerToken } from "./api";

// Il widget Google Picker (script ufficiale Google) non ha tipi propri nel
// progetto: dichiarazione minima solo per la superficie usata qui, non
// l'intera API — evita `any` diffuso mantenendo la dipendenza leggera.
interface GooglePickerDoc {
  id: string;
  name: string;
}
interface GooglePickerCallbackData {
  action: string;
  docs?: GooglePickerDoc[];
}
interface GooglePickerView {
  setSelectFolderEnabled(enabled: boolean): GooglePickerView;
  setIncludeFolders(include: boolean): GooglePickerView;
}
interface GooglePickerBuilder {
  addView(view: GooglePickerView): GooglePickerBuilder;
  setOAuthToken(token: string): GooglePickerBuilder;
  setDeveloperKey(key: string): GooglePickerBuilder;
  setCallback(callback: (data: GooglePickerCallbackData) => void): GooglePickerBuilder;
  build(): { setVisible(visible: boolean): void };
}
interface GooglePickerNamespace {
  DocsView: new (viewId: unknown) => GooglePickerView;
  ViewId: { FOLDERS: unknown };
  Action: { PICKED: string };
  PickerBuilder: new () => GooglePickerBuilder;
}
interface GapiNamespace {
  load(api: "picker", options: { callback: () => void }): void;
}

declare global {
  interface Window {
    gapi?: GapiNamespace;
    google?: { picker: GooglePickerNamespace };
  }
}

const PICKER_SCRIPT_SRC = "https://apis.google.com/js/api.js";
const PICKER_API_KEY = import.meta.env.VITE_GOOGLE_PICKER_API_KEY;

let scriptLoadPromise: Promise<void> | null = null;

function loadGooglePickerScript(): Promise<void> {
  if (window.google?.picker) return Promise.resolve();
  if (scriptLoadPromise) return scriptLoadPromise;
  scriptLoadPromise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = PICKER_SCRIPT_SRC;
    script.async = true;
    script.onload = () => window.gapi?.load("picker", { callback: () => resolve() });
    script.onerror = () => reject(new Error("Impossibile caricare Google Picker"));
    document.body.appendChild(script);
  });
  return scriptLoadPromise;
}

export interface PickedFolder {
  id: string;
  name: string;
}

interface DriveFolderPickerButtonProps {
  label: string;
  variant?: "primary" | "secondary" | "ghost";
  onPicked: (folder: PickedFolder) => void;
  onError?: (message: string) => void;
}

/** Bottone che apre il widget Google Picker (ufficiale, script caricato solo
 * on-demand alla prima apertura) in modalità selezione cartella — mai un
 * campo di testo libero per il path (SPEC_FE: tutto guidato). Riusato sia
 * nel wizard di connessione sia in `ExportOptionsDialog` ("Cambia cartella"). */
export function DriveFolderPickerButton({ label, variant = "secondary", onPicked, onError }: DriveFolderPickerButtonProps) {
  const [loading, setLoading] = useState(false);

  const openPicker = useCallback(async () => {
    if (!PICKER_API_KEY) {
      onError?.("Google Picker non configurato su questa istanza.");
      return;
    }
    setLoading(true);
    try {
      const [{ access_token: accessToken }] = await Promise.all([
        fetchGooglePickerToken(),
        loadGooglePickerScript(),
      ]);
      const picker = window.google!.picker;
      const view = new picker.DocsView(picker.ViewId.FOLDERS).setSelectFolderEnabled(true).setIncludeFolders(true);
      new picker.PickerBuilder()
        .addView(view)
        .setOAuthToken(accessToken)
        .setDeveloperKey(PICKER_API_KEY)
        .setCallback((data) => {
          if (data.action === picker.Action.PICKED && data.docs?.[0]) {
            onPicked({ id: data.docs[0].id, name: data.docs[0].name });
          }
        })
        .build()
        .setVisible(true);
    } catch {
      onError?.("Non è stato possibile aprire il selettore di cartelle Google Drive.");
    } finally {
      setLoading(false);
    }
  }, [onPicked, onError]);

  return (
    <Button variant={variant} size="sm" loading={loading} onClick={() => void openPicker()}>
      {label}
    </Button>
  );
}
