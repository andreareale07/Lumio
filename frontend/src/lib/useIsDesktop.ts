import { useEffect, useState } from "react";

const DESKTOP_QUERY = "(min-width: 768px)";

/** `true` da `md` in su (stesso breakpoint di Tailwind): li' i pannelli sono
 * popover ancorati, sotto sono bottom sheet. */
export function useIsDesktop(): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(DESKTOP_QUERY).matches);
  useEffect(() => {
    const media = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => setMatches(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return matches;
}
