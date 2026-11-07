/// <reference types="vite/client" />
/// <reference types="vite-plugin-pwa/react" />

interface ImportMetaEnv {
  readonly VITE_APP_NAME: string;
  readonly VITE_APP_TAGLINE: string;
  /** Milestone 10: Browser key ristretta alla Google Picker API — mai il
   * client OAuth (quello resta lato backend, mai esposto al frontend). */
  readonly VITE_GOOGLE_PICKER_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** Versione dell'app da package.json (iniettata da Vite). */
declare const __APP_VERSION__: string;
