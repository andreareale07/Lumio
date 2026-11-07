/** L'URL di autorizzazione arriva dal provider tramite il backend e porta il
 * browser fuori da Lumio: solo https (http solo verso localhost, per il mock di
 * sviluppo). Uno schema come `javascript:` eseguirebbe codice nell'origine
 * dell'app. Controllo ripetuto qui oltre che nel backend (difesa a due livelli). */
export function isSafeAuthorizeUrl(value: string): boolean {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return false;
  }
  if (url.username || url.password) return false;
  if (url.protocol === "https:") return true;
  return url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
}
