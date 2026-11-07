// Applica il tema salvato PRIMA del primo paint (SPEC_FE §63: evitare il flash
// del tema al caricamento). File esterno e non script inline: la CSP di nginx
// non ammette script inline.
(function () {
  try {
    var stored = localStorage.getItem("lumio-theme");
    if (stored === "light" || stored === "dark") {
      document.documentElement.setAttribute("data-theme", stored);
    }
  } catch (e) {
    /* localStorage non disponibile (es. modalita' privata): fallback al tema di sistema */
  }
})();
