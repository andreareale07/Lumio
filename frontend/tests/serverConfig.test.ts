import { describe, expect, it } from "vitest";

import { isInsecureRemote, normalizeServerUrl } from "../src/lib/serverConfig";

describe("normalizeServerUrl", () => {
  it("assume https senza schema e toglie percorso e slash finale", () => {
    expect(normalizeServerUrl("lumio.example.com/")).toEqual({ ok: true, url: "https://lumio.example.com" });
    expect(normalizeServerUrl("https://lumio.example.com/app?x=1")).toEqual({
      ok: true,
      url: "https://lumio.example.com",
    });
  });

  it("mantiene http e porta per i server in LAN", () => {
    expect(normalizeServerUrl("http://192.168.1.20:5173")).toEqual({ ok: true, url: "http://192.168.1.20:5173" });
  });

  it("rifiuta vuoto e schemi non web", () => {
    expect(normalizeServerUrl("   ")).toEqual({ ok: false, reason: "empty" });
    expect(normalizeServerUrl("ftp://example.com")).toEqual({ ok: false, reason: "invalid" });
  });
});

describe("isInsecureRemote", () => {
  it("segnala solo http verso host pubblici", () => {
    expect(isInsecureRemote("http://lumio.example.com")).toBe(true);
    expect(isInsecureRemote("https://lumio.example.com")).toBe(false);
    expect(isInsecureRemote("http://192.168.1.20:5173")).toBe(false);
    expect(isInsecureRemote("http://10.0.0.5")).toBe(false);
    expect(isInsecureRemote("http://lumio.local")).toBe(false);
  });
});
