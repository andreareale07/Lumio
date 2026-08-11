import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, setAccessToken, setUnauthorizedHandler } from "../src/lib/apiClient";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiClient", () => {
  beforeEach(() => {
    setAccessToken(null);
    setUnauthorizedHandler(null);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("include l'access token nell'header Authorization", async () => {
    setAccessToken("token-123");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ok: true }));

    await api.get("/accounts");

    const [, options] = fetchMock.mock.calls[0];
    expect((options?.headers as Record<string, string>)["Authorization"]).toBe("Bearer token-123");
  });

  it("su 401 tenta un refresh e ritenta la richiesta originale", async () => {
    setAccessToken("expired-token");
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(jsonResponse({ access_token: "new-token" }))
      .mockResolvedValueOnce(jsonResponse([{ id: "1" }]));

    const result = await api.get("/accounts");

    expect(result).toEqual([{ id: "1" }]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const retryCall = fetchMock.mock.calls[2];
    expect((retryCall[1]?.headers as Record<string, string>)["Authorization"]).toBe("Bearer new-token");
  });

  it("se anche il refresh fallisce, notifica l'handler di unauthorized e propaga l'errore", async () => {
    setAccessToken("expired-token");
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }));

    const onUnauthorized = vi.fn();
    setUnauthorizedHandler(onUnauthorized);

    await expect(api.get("/accounts")).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it("propaga il messaggio di errore del backend per le risposte non-ok", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ detail: "Invalid category_id" }, 400));

    await expect(api.post("/rules", {})).rejects.toMatchObject({ status: 400, message: "Invalid category_id" });
  });
});
