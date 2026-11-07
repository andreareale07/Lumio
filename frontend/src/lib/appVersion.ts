/** Versione dell'app (da `package.json`, iniettata da Vite). */
export const APP_VERSION: string = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "dev";
