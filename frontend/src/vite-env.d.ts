/// <reference types="vite/client" />

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
