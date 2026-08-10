import { expect, test } from "@playwright/test";

test("la home page mostra il nome del prodotto", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Lumio");
});
