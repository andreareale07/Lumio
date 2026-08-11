import "@testing-library/jest-dom/vitest";

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
