import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("right-clicking any surface of the app never raises the browser context menu", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator(".main-topbar")).toBeVisible();

  const spots = [
    ".app",
    ".sidebar",
    ".main-topbar",
    ".main-scroll",
    "textarea",
    ".main-workspace",
  ];
  for (const selector of spots) {
    const blocked = await page.locator(selector).first().evaluate((node) => {
      const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
      node.dispatchEvent(event);
      return event.defaultPrevented;
    });
    expect(blocked, `contextmenu on ${selector}`).toBe(true);
  }
});

test("an embedded artifact preview blocks it too", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder(/Ask your study partner/).fill("hello");
  await page.getByRole("button", { name: "Send" }).click();
  await page.getByTestId("rail-toggle-artifacts").click();
  await page.locator(".artifact-row", { hasText: "security-review.html" }).click();
  await expect(page.getByTestId("artifact-frame")).toBeVisible();

  const blocked = await page
    .frameLocator('[data-testid="artifact-frame"]')
    .locator("html")
    .evaluate((node) => {
      const event = new MouseEvent("contextmenu", { bubbles: true, cancelable: true });
      node.dispatchEvent(event);
      return event.defaultPrevented;
    });
  expect(blocked).toBe(true);
});
