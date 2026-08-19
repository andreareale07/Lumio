import "@testing-library/jest-dom/vitest";

// Locale deterministico nei test (jsdom di default riporta
// `navigator.language` = "en-US", diverso dall'ambiente reale) — va
// impostato PRIMA di importare `app/i18n`, che legge localStorage in modo
// sincrono al momento dell'init: import dinamico per sequenziare
// correttamente (un `import` statico verrebbe sempre issato prima di
// qualunque altra istruzione, localStorage compreso).
localStorage.setItem("lumio-locale", "it");
await import("../src/app/i18n");

// jsdom non implementa matchMedia (usato da useChartTheme per seguire il
// tema di sistema, milestone 08) — polyfill minimo valido per i test.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
