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

// Sample [nav right edge, surface left edge] on every animation frame around `trigger`, so a test
// can tell a synchronized slide from a snap. The surface is the in-flow element beside the nav —
// every overlay child of .app is positioned, so filtering on static/relative finds exactly one.
async function navAnimationFrames(page, trigger) {
  const sampling = page.evaluate(async () => {
    const frames = [];
    const start = performance.now();
    await new Promise((resolve) => {
      const tick = () => {
        const sidebar = document.querySelector(".sidebar");
        const surface = Array.from(document.querySelectorAll(".app > :not(.sidebar)")).find(
          (el) => {
            const pos = getComputedStyle(el).position;
            return pos === "static" || pos === "relative";
          },
        );
        if (sidebar && surface) {
          frames.push([
            sidebar.getBoundingClientRect().right,
            surface.getBoundingClientRect().left,
          ]);
        }
        if (performance.now() - start > 1400) resolve(undefined);
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return frames;
  });
  await trigger();
  return sampling;
}

function expectSynchronizedNav(frames, from, to) {
  const edges = frames.map(([, left]) => left);
  expect(Math.abs(edges[0] - from)).toBeLessThanOrEqual(5);
  expect(Math.abs(edges[edges.length - 1] - to)).toBeLessThanOrEqual(1);
  // The content never outruns the nav: they share an edge on every frame.
  for (const [navRight, surfaceLeft] of frames) {
    expect(Math.abs(navRight - surfaceLeft)).toBeLessThanOrEqual(1);
  }
  // And it gets there through intermediate widths rather than snapping in one jump.
  const lo = Math.min(from, to);
  const hi = Math.max(from, to);
  expect(edges.filter((l) => l > lo + 1 && l < hi - 1).length).toBeGreaterThanOrEqual(3);
}

test("collapsing slides the nav out while the content grows in sync", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".sidebar")).toBeVisible();
  const frames = await navAnimationFrames(page, async () => {
    await page.getByRole("button", { name: "Collapse sidebar" }).click();
  });
  expectSynchronizedNav(frames, 300, 0);
});

test("expanding slides the nav in while the content narrows in sync", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect(page.locator(".app")).toHaveClass(/nav-collapsed/);
  await page.waitForTimeout(450);

  const frames = await navAnimationFrames(page, async () => {
    await page.getByTestId("topbar-cluster").getByRole("button", { name: "Show sidebar" }).click();
  });
  expectSynchronizedNav(frames, 0, 300);
});

// Every surface shares the flex row with the nav, so the fix is structural — but each full-page
// one is checked anyway: a page with its own absolute chrome could still snap.
const NAV_SURFACES = [
  ["Automations", async (page) => { await page.getByTestId("nav-automations").click(); }],
  [
    "Activity",
    async (page) => {
      await page.getByTestId("account-row").click();
      await page.getByRole("button", { name: "Activity", exact: true }).click();
    },
  ],
  [
    "Connectors",
    async (page) => {
      await page.getByTestId("account-row").click();
      await page.getByRole("button", { name: "Connectors", exact: true }).click();
    },
  ],
  ["Inbox", async (page) => { await page.getByTestId("inbox-chip").click(); }],
];

for (const [name, open] of NAV_SURFACES) {
  test(`the ${name} surface reclaims width in sync with the nav`, async ({ page }) => {
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeVisible();
    await open(page);
    await expect(page.locator(".app > main")).toBeVisible();

    const frames = await navAnimationFrames(page, async () => {
      await page.keyboard.press("Meta+b");
    });
    expectSynchronizedNav(frames, 300, 0);
  });
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
