import { describe, expect, it } from "vitest";

import { isSafeAuthorizeUrl } from "../src/features/settings/open-banking/safeUrl";

describe("isSafeAuthorizeUrl", () => {
  it("accetta https", () => {
    expect(isSafeAuthorizeUrl("https://auth.example/start?x=1")).toBe(true);
  });

  it("rifiuta schemi eseguibili o non cifrati", () => {
    expect(isSafeAuthorizeUrl("javascript:alert(document.domain)")).toBe(false);
    expect(isSafeAuthorizeUrl("data:text/html,<script>alert(1)</script>")).toBe(false);
    expect(isSafeAuthorizeUrl("http://bank.example/auth")).toBe(false);
    expect(isSafeAuthorizeUrl("//bank.example/auth")).toBe(false);
  });

  it("rifiuta credenziali incorporate e valori non URL", () => {
    expect(isSafeAuthorizeUrl("https://user:pw@bank.example/")).toBe(false);
    expect(isSafeAuthorizeUrl("")).toBe(false);
    expect(isSafeAuthorizeUrl("non un url")).toBe(false);
  });

  it("ammette http solo verso localhost (mock di sviluppo)", () => {
    expect(isSafeAuthorizeUrl("http://localhost:9999/auth")).toBe(true);
  });
});
