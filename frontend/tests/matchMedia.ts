/** Imposta se `matchMedia` risponde "desktop" (min-width: 768px) o "mobile"
 * (default dei test: jsdom non ha un viewport). I componenti che scelgono fra
 * popover e bottom sheet leggono `useIsDesktop`. */
export function setDesktop(isDesktop: boolean): void {
  window.matchMedia = ((query: string) =>
    ({
      matches: isDesktop,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
}
