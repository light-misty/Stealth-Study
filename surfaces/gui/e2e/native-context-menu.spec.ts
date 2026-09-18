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
