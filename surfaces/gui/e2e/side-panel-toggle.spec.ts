import { expect, type Page } from "@playwright/test";
import { test } from "./fixtures";

// The desktop shell's window-drag region must never swallow a topbar control's click:
// tao's drag_window() calls ReleaseCapture() + posts WM_NCLBUTTONDOWN, so the webview
// loses the in-flight mouse and the button's onClick never runs.

async function installShell(page: Page) {
  await page.addInitScript(() => {
    (window as any).__OCW_PLATFORM__ = "windows";
    (window as any).__shellCalls = [] as string[];
    (window as any).__TAURI__ = {
      core: {
        invoke: (cmd: string) => {
          (window as any).__shellCalls.push(cmd);
          return Promise.resolve(cmd === "start_window_drag" ? true : null);
        },
      },
    };
  });
}

const dragCalls = (page: Page) =>
  page.evaluate(() => (window as any).__shellCalls.filter((c: string) => c === "start_window_drag").length);

async function openNewSessionPage(page: Page) {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("ocw-e2e-rail-default", "1");
    localStorage.removeItem("coworker:rail-hidden:v1");
  });
  await page.reload();
  await page.getByText("New session").first().click();
  await expect(page.getByText("What are we studying today?")).toBeVisible();
}

test("the side-panel toggle opens and closes the rail on the new-session page", async ({ page }) => {
  await installShell(page);
  await openNewSessionPage(page);

  await expect(page.locator(".right-rail")).toHaveClass(/rail-off/);
  await page.getByRole("button", { name: "Show side panel" }).click();
  await expect(page.locator(".right-rail")).not.toHaveClass(/rail-off/);
  await expect(page.locator(".right-rail .rail-section-toggle").first()).toBeVisible();
  await expect(page.locator(".main")).toHaveClass(/rail-open/);

  await page.getByRole("button", { name: "Hide side panel" }).click();
  await expect(page.locator(".right-rail")).toHaveClass(/rail-off/);
  await expect(page.locator(".main")).not.toHaveClass(/rail-open/);

  await page.getByRole("button", { name: "Show side panel" }).click();
  await expect(page.locator(".right-rail")).not.toHaveClass(/rail-off/);

  expect(await dragCalls(page), "a topbar click asked the shell to drag the window").toBe(0);
});

test("the hide toggle lands exactly where the show toggle was", async ({ page }) => {
  await installShell(page);
  await openNewSessionPage(page);

  const show = page.getByRole("button", { name: "Show side panel" });
  const showBox = await show.boundingBox();
  await show.click();

  const wobble: string[] = [];
  for (let i = 0; i < 10; i++) {
    const mid = await page
      .getByRole("button", { name: "Hide side panel" })
      .boundingBox()
      .catch(() => null);
    if (mid) wobble.push(`${Math.round(mid.x)},${Math.round(mid.y)}`);
    await page.waitForTimeout(15);
  }
  expect(new Set(wobble).size, `the toggle wobbled: ${wobble.join(" -> ")}`).toBe(1);

  await expect(page.locator(".right-rail")).not.toHaveClass(/rail-off/);
  await page.waitForTimeout(300); // let the rail slide settle before measuring

  const hide = page.getByRole("button", { name: "Hide side panel" });
  await expect(hide).toBeVisible();
  const hideBox = await hide.boundingBox();
  expect(Math.abs(hideBox!.x - showBox!.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(hideBox!.y - showBox!.y)).toBeLessThanOrEqual(1);

  const rail = await page.locator(".right-rail").boundingBox();
  expect(
    Math.abs(rail!.x + rail!.width - (hideBox!.x + hideBox!.width) - 14),
  ).toBeLessThanOrEqual(1);

  await hide.click();
  await expect(page.locator(".right-rail")).toHaveClass(/rail-off/);
  expect(await dragCalls(page)).toBe(0);
});

test("an empty stretch of the topbar still starts the window drag", async ({ page }) => {
  await installShell(page);
  await openNewSessionPage(page);

  const box = await page.locator(".main-topbar-actions").boundingBox();
  const x = box.x + 6;
  const y = box.y + box.height / 2;
  const onControl = await page.evaluate(([px, py]) => {
    const hit = document.elementFromPoint(px, py);
    return hit === null || hit.closest("button, input, textarea, select, a") !== null;
  }, [x, y]);
  expect(onControl, "the probe point landed on a control").toBe(false);

  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.up();
  expect(await dragCalls(page)).toBe(1);
});

test("every control in the topbar's collapsed cluster stays clickable", async ({ page }) => {
  await installShell(page);
  await openNewSessionPage(page);

  await page.keyboard.press("Control+b");
  const cluster = page.getByTestId("topbar-cluster");
  await expect(cluster).toBeVisible();
  await cluster.getByRole("button", { name: "Search" }).click();
  await expect(page.getByPlaceholder("Search chats")).toBeVisible();
  await page.keyboard.press("Escape");
  await cluster.getByRole("button", { name: "New session" }).click();
  await expect(page.getByText("What are we studying today?")).toBeVisible();
  await cluster.getByRole("button", { name: "Show sidebar" }).click();
  await expect(page.locator(".app")).not.toHaveClass(/nav-collapsed/);
  expect(await dragCalls(page)).toBe(0);
});

test("the topbar Artifacts entry reopens the rail without starting a window drag", async ({
  page,
}) => {
  await installShell(page);
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("ocw-e2e-rail-default", "1");
    localStorage.setItem("coworker:rail-hidden:v1", "1");
  });
  await page.reload();
  await page.getByPlaceholder(/Ask your study partner/).fill("show the report");
  await page.getByRole("button", { name: "Send" }).click();

  const artifacts = page.locator(".topbar-artifacts-btn");
  await expect(artifacts).toBeVisible();
  await artifacts.click();
  await expect(page.locator(".right-rail")).toBeVisible();
  expect(await dragCalls(page)).toBe(0);
});

for (const size of [
  { width: 1440, height: 900 },
  { width: 980, height: 640 },
]) {
  test(`the side-panel toggle works at ${size.width}x${size.height}`, async ({ page }) => {
    await installShell(page);
    await page.setViewportSize(size);
    await openNewSessionPage(page);

    await page.getByRole("button", { name: "Show side panel" }).click();
    const rail = page.locator(".right-rail");
    await expect(rail).not.toHaveClass(/rail-off/);
    await expect(async () => {
      const railBox = await rail.boundingBox();
      expect(railBox.width).toBeGreaterThan(0);
      expect(railBox.x + railBox.width).toBeLessThanOrEqual(size.width + 1);
    }).toPass();
    const topbar = await page.locator(".main-topbar").boundingBox();
    // The toggle stays reachable beside the rail (the topbar stops where the rail begins).
    await page.getByRole("button", { name: "Hide side panel" }).click();
    await expect(page.locator(".right-rail")).toHaveClass(/rail-off/);
    await page.getByRole("button", { name: "Show side panel" }).click();
    await expect(page.locator(".main-topbar")).toBeVisible();
    expect(topbar.width).toBeLessThan(size.width);
    expect(await dragCalls(page)).toBe(0);
  });
}
