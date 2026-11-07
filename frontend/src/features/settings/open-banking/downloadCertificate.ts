/** Scarica il certificato PUBBLICO (mai la chiave privata, che non lascia il server). */
export function downloadCertificate(pem: string) {
  const url = URL.createObjectURL(new Blob([pem], { type: "application/x-pem-file" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "lumio-enablebanking.pem";
  link.click();
  URL.revokeObjectURL(url);
}
