import { expect } from "@playwright/test";
import { test } from "./fixtures";

// E2E smoke for the campus exam-prep stations (08 §7 E2E-1..E2E-8). Each case drives the
// real UI against the mocked /v1/campus routes in fixtures.ts.

async function createProfile(
  page: import("@playwright/test").Page,
  opts: { title: string; examDate?: string },
) {
  await page.getByTestId("campus-profile-create-title").fill(opts.title);
  if (opts.examDate) {
    await page.getByTestId("campus-profile-create-exam-date").fill(opts.examDate);
  }
  await page.getByTestId("campus-profile-create-submit").click();
  await expect(page.getByTestId("campus-station")).toBeVisible();
}

// E2E-1: three-station navigation — empty-state create card renders on first run.
test("campus: the three stations navigate cleanly and render the empty-state create card", async ({
  page,
}) => {
  await page.goto("/");
  for (const track of ["cet", "kaoyan", "cert"] as const) {
    await page.getByTestId(`nav-campus-${track}`).click();
    await expect(page.getByTestId("campus-station-empty")).toBeVisible();
    await expect(page.getByTestId("campus-station-empty")).toHaveAttribute("data-track", track);
    await expect(page.getByTestId("campus-profile-create-card")).toBeVisible();
  }
  // Round-trip back to a classic surface still works.
  await page.getByTestId("topbar-cluster").click();
  await expect(page.getByPlaceholder(/Ask the coworker/)).toBeVisible();
});

// E2E-2: CET grading main path.
test("campus: create a CET profile then grade an essay — result shows dimensions and errors", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "四级冲关", examDate: "2026-12-18" });

  await page.getByTestId("campus-cet-grading-text").fill("The important of study.");
  await page.getByTestId("campus-cet-grading-submit").click();
  await expect(page.getByTestId("campus-grading-result")).toBeVisible();
  await expect(page.getByTestId("campus-grading-dimension").first()).toBeVisible();
  await expect(page.getByTestId("campus-grading-error").first()).toBeVisible();
});

// E2E-3: CET assessment paper.
test("campus: start a CET assessment, answer five questions, interrupt, and resume", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "四级定级" });
  await page.getByTestId("campus-cet-assessment-start").click();
  await expect(page.getByTestId("campus-cet-assessment-progress")).toBeVisible();

  // Paper mode renders every question on one screen — click each option to register answers.
  const options = page.getByTestId("campus-cet-assessment-option");
  const count = await options.count();
  for (let i = 0; i < Math.min(5, count); i++) {
    await options.nth(i).click();
  }
  await expect(page.getByTestId("campus-cet-assessment-progress")).toContainText("5");

  // Reload — the persisted assessment resumes with answers intact.
  await page.reload();
  await page.getByTestId("nav-campus-cet").click();
  await expect(page.getByTestId("campus-cet-assessment-progress")).toContainText("5");
});

// E2E-4: KY plan generation -> reschedule -> weekly report.
test("campus: generate a kaoyan plan, reschedule, open the weekly report", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-kaoyan").click();
  await createProfile(page, { title: "考研规划" });

  await page.getByTestId("campus-plan-generate").click();
  await expect(page.getByTestId("campus-kaoyan-plan-panel")).toBeVisible();
  await expect(page.getByTestId("campus-kaoyan-ring")).toBeVisible();

  await page.getByTestId("campus-plan-reschedule").click();
  await expect(page.getByTestId("campus-kaoyan-plan-panel")).toBeVisible();

  await page.getByTestId("campus-weekly-generate").click();
  await expect(page.getByTestId("campus-weekly-view")).toBeVisible();
});

// E2E-5: KY library import + citation-bearing QA.
test("campus: import a document then ask a library question — citations are clickable", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-kaoyan").click();
  await createProfile(page, { title: "考研资料" });

  await page.getByTestId("campus-library-import").setInputFiles({
    name: "notes.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# 考研英语\n\n长难句分析示范。"),
  });
  await expect(page.getByTestId("campus-library-row")).toBeVisible();

  await page.getByTestId("campus-qa-input").fill("这个句子的主干是什么？");
  await page.getByTestId("campus-qa-send").click();
  await expect(page.getByTestId("campus-qa-answer")).toBeVisible();
  await expect(page.getByTestId("campus-citation").first()).toBeVisible();
});

// E2E-6: CERT knowledge tree + subjective grading.
test("campus: generate a CERT knowledge tree and grade a subjective answer", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cert").click();
  await createProfile(page, { title: "教资备考" });

  await page.getByTestId("campus-cert-setup-create").click();
  await expect(page.getByTestId("campus-cert-tree-panel")).toBeVisible();
  await expect(page.getByTestId("campus-cert-tree-node").first()).toBeVisible();
  await expect(page.getByTestId("campus-cert-tree-coverage")).toBeVisible();

  await page.getByTestId("campus-cert-grading-answer").fill("参考答案要点分析...");
  await page.getByTestId("campus-cert-grading-submit").click();
  await expect(page.getByTestId("campus-cert-grading-state").first()).toBeVisible();
  await expect(page.getByTestId("campus-grading-dimension").first()).toBeVisible();
});

// E2E-7: global flag regression (F-1/F-2/F-4).
test("campus: with voice + login flags off by default, no mic / sign-in affordance renders on campus", async ({
  page,
}) => {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.setItem("ocw.flag.voice", "0");
    localStorage.setItem("ocw.flag.login", "0");
  });
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await expect(page.getByTestId("campus-station-empty")).toBeVisible();
  // No mic / cloud-signin affordance exists on the campus surface.
  await expect(page.locator('[data-testid*="mic"]')).toHaveCount(0);
  await expect(page.locator('[data-testid*="cloud-signin"]')).toHaveCount(0);
});

// E2E-8: CET mock-exam stage lock.
test("campus: advance a CET mock exam past writing into the listening lock", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "模考演练" });

  await page.getByTestId("campus-mock-start").click();
  await expect(page.getByTestId("campus-mock-timer")).toBeVisible();

  // Fast-forward the writing timer (dev hook), which reveals the advance button.
  await page.getByTestId("fast-forward-hook").click();
  await expect(page.getByTestId("campus-mock-advance")).toBeVisible();
  await page.getByTestId("campus-mock-advance").click();
  await expect(page.getByTestId("campus-mock-stage")).toHaveAttribute("data-stage", "listening");
  // Writing stage completed -> writing textarea is disabled (locked).
  await expect(page.getByTestId("campus-mock-essay")).toBeDisabled();
});
