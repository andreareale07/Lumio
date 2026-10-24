import { QueryClient } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { scheduleActivityRefresh } from "../src/lib/activityRefresh";

describe("scheduleActivityRefresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("rilegge le attivita' subito e poi ancora qualche volta, per coprire la partenza del job", async () => {
    const client = new QueryClient();
    const spy = vi.spyOn(client, "invalidateQueries").mockResolvedValue();

    scheduleActivityRefresh(client);
    await vi.advanceTimersByTimeAsync(0);
    expect(spy).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(5000);
    expect(spy).toHaveBeenCalledTimes(4);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["activity"] });

    await vi.advanceTimersByTimeAsync(60000);
    expect(spy).toHaveBeenCalledTimes(4);
  });
});
