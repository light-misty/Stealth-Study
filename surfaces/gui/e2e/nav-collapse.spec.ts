// Left-nav polish (§20): collapse (⌘B / brand button → reveal button docks it back) and the
// RECENT-header group/filter popover (Group by Persona↔Chronological, Filter by coworker).
import { expect } from "@playwright/test";
import { test } from "./fixtures";

test("collapse hides the sidebar and reclaims the width; reveal button docks it back", async ({
  page,
}) => {
  await page.goto("/");
  const app = page.locator(".app");
  await expect(page.locator(".sidebar")).toBeVisible();

  // Collapse via the brand button.
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(app).toHaveClass(/nav-collapsed/);
  // The floating reveal affordance appears; clicking it docks the nav back.
  const reveal = page.getByRole("button", { name: "Show sidebar" });
  await expect(reveal).toBeVisible();
  await reveal.click();
  await expect(app).not.toHaveClass(/nav-collapsed/);
});

test("⌘B toggles the sidebar collapse", async ({ page }) => {
  await page.goto("/");
  const app = page.locator(".app");
  await page.keyboard.press("Meta+b");
  await expect(app).toHaveClass(/nav-collapsed/);
  await page.keyboard.press("Meta+b");
  await expect(app).not.toHaveClass(/nav-collapsed/);
});

// The collapsed nav is off-screen to the left: its right edge never crosses x=0.
async function sidebarRightEdge(page) {
  const box = await page.locator(".sidebar").boundingBox();
  return box.x + box.width;
}

test("collapsing leaves no hover-trigger zone in the DOM", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.locator(".app")).toHaveClass(/nav-collapsed/);
  await expect(page.locator(".nav-hover-zone")).toHaveCount(0);
});

test("hovering the left edge while collapsed never peeks the nav back", async ({ page }) => {
  await page.goto("/");
  const app = page.locator(".app");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(app).toHaveClass(/nav-collapsed/);
  await expect.poll(() => sidebarRightEdge(page)).toBeLessThanOrEqual(1);

  for (const y of [60, 240, 480, 700]) {
    await page.mouse.move(0, y);
    await page.waitForTimeout(120);
    expect(await sidebarRightEdge(page)).toBeLessThanOrEqual(1);
    expect(await app.getAttribute("class")).not.toMatch(/nav-peek/);
  }

  // Sliding in from deeper inside the content edge is the other way a peek used to fire.
  await page.mouse.move(120, 400);
  await page.mouse.move(2, 400);
  await page.waitForTimeout(300);
  expect(await sidebarRightEdge(page)).toBeLessThanOrEqual(1);

  // Only an explicit action brings it back.
  await page.getByTestId("topbar-cluster").getByRole("button", { name: "Show sidebar" }).click();
  await expect(app).not.toHaveClass(/nav-collapsed/);
});

test("RECENT header group/filter popover: switch grouping + see coworker filters", async ({
  page,
}) => {
  await page.goto("/");
  const header = page.getByTestId("recent-header");
  await expect(header).toContainText("Recent");

  await header.getByRole("button", { name: "Group and filter conversations" }).click();
  const menu = page.getByTestId("group-filter-menu");
  await expect(menu).toContainText("Group by");
  await expect(menu).toContainText("Filter by coworker");

  // Switch to Chronological → the persona accordion collapses into a flat list (the "StealthStudy"
  // persona group header is no longer a row; sessions list directly).
  await menu.getByText("Chronological").click();
  await expect(menu.getByText("Chronological").locator("xpath=..")).toContainText("✓");

  // Filter-by-coworker checkboxes are present (none checked by default → all shown).
  await expect(menu).toContainText("None checked shows all.");
});
