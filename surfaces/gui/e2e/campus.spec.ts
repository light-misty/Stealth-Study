import { expect } from "@playwright/test";
import { test } from "./fixtures";

// E2E smoke for the campus exam-prep stations (08 §7 E2E-1..E2E-8). Each case drives the
// real UI against the mocked /v1/campus routes in fixtures.ts, whose shapes mirror the live
// backend (see the campus contract probe in `docs/dev/交付文档/`). Selectors follow the
// `campus-<domain>-<action>` convention, so a control that two panels render carries a
// domain-qualified testid (essay vs translation workshop).

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

// The station shows one module per screen, so a journey that ends in a panel has to take that
// panel's tab first. The tab strip is TRACK_PANELS order, keyed by panel key.
async function openTab(page: import("@playwright/test").Page, key: string) {
  const tab = page.getByTestId(`campus-station-tab-${key}`);
  await tab.click();
  await expect(tab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByTestId(`campus-station-pane-${key}`)).toBeVisible();
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
  // Round-trip back to a classic surface still works: opening a session from the sidebar
  // unmounts the station and restores the conversation composer.
  await page.getByTitle("Weekly plan 1").click();
  await expect(page.getByPlaceholder(/Ask your study partner/)).toBeVisible();
  await expect(page.getByTestId("campus-station-empty")).toHaveCount(0);
});

test("sidebar: the campus station rows share the nav rows' vertical rhythm", async ({ page }) => {
  await page.goto("/");
  const order = [
    "nav-new-session",
    "nav-search",
    "nav-automations",
    "nav-campus-cet",
    "nav-campus-kaoyan",
    "nav-campus-cert",
  ];
  const boxes = [];
  for (const id of order) {
    const box = await page.getByTestId(id).boundingBox();
    expect(box, `${id} is not laid out`).not.toBeNull();
    boxes.push(box!);
  }
  const gaps = boxes
    .slice(1)
    .map((box, i) => Math.round(box.y - (boxes[i].y + boxes[i].height)));
  expect(gaps[0]).toBeGreaterThan(0);
  expect(gaps).toEqual(gaps.map(() => gaps[0]));
});

// E2E-2: CET grading main path.
test("campus: create a CET profile then grade an essay — result shows dimensions and errors", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "四级冲关", examDate: "2026-12-18" });

  await openTab(page, "essay");
  await page.getByTestId("campus-cet-essay-grading-text").fill("The important of study.");
  await page.getByTestId("campus-cet-essay-grading-submit").click();
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

  await openTab(page, "assessment");
  await page.getByTestId("campus-cet-assessment-start").click();
  await expect(page.getByTestId("campus-cet-assessment-progress")).toBeVisible();

  // Paper mode renders every question on one screen. Each question is its own card holding its
  // own options, so answering five questions means taking the first option of the first five
  // cards — clicking five *option elements* would only reach two and a half cards.
  const questions = page.getByTestId("campus-cet-assessment-question");
  await expect(questions).toHaveCount(20);
  for (let i = 0; i < 5; i++) {
    await questions.nth(i).getByTestId("campus-cet-assessment-option").first().click();
  }
  await expect(page.getByTestId("campus-cet-assessment-progress")).toHaveAttribute(
    "data-answered",
    "5",
  );

  // Answers are autosaved on a 400ms debounce, so "interrupt and resume" is only meaningful
  // once the save has landed — the panel's own saved marker is that signal.
  await expect(page.getByTestId("campus-cet-assessment-saved")).toBeVisible();

  // Reload — the persisted assessment resumes with answers intact. Re-entering the station
  // lands on its first tab, so the paper is one tab away rather than on screen.
  await page.reload();
  await page.getByTestId("nav-campus-cet").click();
  await openTab(page, "assessment");
  await expect(page.getByTestId("campus-cet-assessment-progress")).toHaveAttribute(
    "data-answered",
    "5",
  );
});

// E2E-4: KY plan generation -> reschedule -> weekly report.
test("campus: generate a kaoyan plan, reschedule, open the weekly report", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-kaoyan").click();
  await createProfile(page, { title: "考研规划" });

  await openTab(page, "plan");
  await page.getByTestId("campus-plan-generate").click();
  await expect(page.getByTestId("campus-kaoyan-plan-panel")).toBeVisible();
  // One ring per track in the progress report, so the count is what "four tracks are live" means.
  await expect(page.getByTestId("campus-kaoyan-ring").first()).toBeVisible();

  // The reorder button only unlocks once the generated plan's tasks are loaded (G1).
  const reschedule = page.getByTestId("campus-plan-reschedule");
  await expect(reschedule).toBeEnabled();
  await reschedule.click();
  await expect(page.getByTestId("campus-plan-notice")).toBeVisible();

  await openTab(page, "weekly");
  await page.getByTestId("campus-weekly-generate").click();
  await expect(page.getByTestId("campus-weekly-view")).toBeVisible();
  await expect(page.getByTestId("campus-weekly-item-report-1")).toBeVisible();
});

// E2E-5: KY library import + citation-bearing QA.
test("campus: import a document then ask a library question — citations are clickable", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-kaoyan").click();
  await createProfile(page, { title: "考研资料" });

  await openTab(page, "library");
  await page.getByTestId("campus-library-import").setInputFiles({
    name: "notes.md",
    mimeType: "text/markdown",
    buffer: Buffer.from("# 考研英语\n\n长难句分析示范。"),
  });
  await expect(page.getByTestId("campus-library-row")).toBeVisible();

  await openTab(page, "qa");
  await page.getByTestId("campus-qa-input").fill("这个句子的主干是什么？");
  await page.getByTestId("campus-qa-send").click();
  await expect(page.getByTestId("campus-qa-answer")).toBeVisible();
  await expect(page.getByTestId("campus-citation").first()).toBeVisible();
});

// E2E-6: CERT knowledge tree + subjective grading.
test("campus: build a CERT knowledge tree and grade a subjective answer", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cert").click();
  await createProfile(page, { title: "教资备考" });

  // The tree is grown from the panel itself: `campus-cert-tree-add-root` opens the inline form
  // (there is no syllabus-upload entry in the UI, which is why 08 §7's `campus-cert-setup-*`
  // steps — those belong to the deadline timeline — never produced a node).
  await openTab(page, "cert_tree");
  await page.getByTestId("campus-cert-tree-add-root").click();
  await page.getByTestId("campus-cert-tree-add-title").fill("第一章 基础");
  await page.getByTestId("campus-cert-tree-add-submit").click();
  await expect(page.getByTestId("campus-cert-tree-panel")).toBeVisible();
  await expect(page.getByTestId("campus-cert-tree-node").first()).toBeVisible();
  await expect(page.getByTestId("campus-cert-tree-coverage")).toBeVisible();

  await openTab(page, "cert_grading");
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

  await openTab(page, "mock");
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

// E2E-9: profile-name conflict. A duplicate name is refused by a dialog that leaves the
// station and the typed-in name alone, and the name is free again once the rival is archived.
test("campus: a duplicate profile name is refused in a dialog, not by the whole page", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "同名档案" });

  await page.getByTestId("campus-profile-create").click();
  await page.getByTestId("campus-profile-create-title").fill("同名档案");
  await page.getByTestId("campus-profile-create-submit").click();

  await expect(page.getByTestId("campus-profile-conflict")).toBeVisible();
  await expect(page.getByTestId("campus-profile-conflict-body")).toContainText(
    "A profile with this title already exists",
  );
  await expect(page.getByTestId("campus-station")).toBeVisible();
  await expect(page.getByTestId("campus-profile-create-title")).toHaveValue("同名档案");
  await expect(page.getByTestId("campus-profile-item")).toHaveCount(1);

  await page.getByTestId("campus-profile-conflict-close").click();
  await expect(page.getByTestId("campus-profile-conflict")).toHaveCount(0);

  await page.getByTestId("campus-profile-create-title").fill("另一个档案");
  await page.getByTestId("campus-profile-create-submit").click();
  await expect(page.getByTestId("campus-profile-item")).toHaveCount(2);
});

// E2E-10: the archived box. Archiving hands the name back, the station keeps an entry to the
// archived profiles, and restoring puts the boxed one back on the desk beside its twin.
test("campus: archive a profile, find it in the archived list and restore it", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "归档演练", examDate: "2026-12-19" });

  await page.locator('[data-testid^="campus-profile-archive-"]').first().click();
  await expect(page.getByTestId("campus-station-empty")).toBeVisible();
  await expect(page.getByTestId("campus-profile-archived-entry")).toBeVisible();

  await createProfile(page, { title: "归档演练" });
  await expect(page.getByTestId("campus-profile-item")).toHaveCount(1);

  await page.getByTestId("campus-profile-archived-entry").click();
  await expect(page.getByTestId("campus-archived-dialog")).toBeVisible();
  await expect(page.getByTestId("campus-archived-list")).toContainText("归档演练");
  await expect(page.locator('[data-testid^="campus-archived-created-"]').first()).toContainText(
    "2026-09-16",
  );

  await page.getByTestId("campus-archived-search").fill("找不到");
  await expect(page.getByTestId("campus-archived-nomatch")).toBeVisible();
  await page.getByTestId("campus-archived-search").fill("");

  await page.getByTestId("campus-archived-filter").selectOption("older");
  await expect(page.getByTestId("campus-archived-nomatch")).toBeVisible();
  await page.getByTestId("campus-archived-filter").selectOption("all");

  await page.locator('[data-testid^="campus-archived-restore-"]').first().click();
  await expect(page.getByTestId("campus-profile-conflict")).toBeVisible();
  await expect(page.getByTestId("campus-profile-conflict-body")).toContainText(
    "A profile with this title already exists",
  );
  const restoredName = page.getByTestId("campus-profile-conflict-title");
  await expect(restoredName).toHaveValue("归档演练 (2)");
  await page.getByTestId("campus-profile-conflict-ok").click();
  await expect(page.getByTestId("campus-profile-conflict")).toHaveCount(0);
  await expect(page.getByTestId("campus-archived-empty")).toBeVisible();
  await page.getByTestId("campus-archived-dialog-close").click();
  await expect(page.getByTestId("campus-profile-item")).toHaveCount(2);
  await expect(page.getByTestId("campus-profile-item").first()).toHaveText("归档演练 (2)");
  await expect(page.getByTestId("campus-profile-archived-entry")).toHaveCount(0);
});

// E2E-11: renaming from the switcher, with the desk's names refused as you type.
test("campus: rename an on-desk profile and refuse a taken name", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-campus-cet").click();
  await createProfile(page, { title: "先建一个" });
  await page.getByTestId("campus-profile-create").click();
  await createProfile(page, { title: "占用中的名字" });

  await expect(page.getByTestId("campus-profile-item").first()).toHaveText("先建一个");
  const renameButton = page.locator('[data-testid^="campus-profile-rename-"]').first();
  await renameButton.click();

  const input = page.getByTestId("campus-profile-rename-input");
  await expect(input).toHaveValue("先建一个");
  await input.fill("占用中的名字");
  await expect(page.getByTestId("campus-profile-rename-error")).toBeVisible();
  await expect(page.getByTestId("campus-profile-rename-save")).toBeDisabled();

  await input.fill("改过的名字");
  await page.getByTestId("campus-profile-rename-save").click();
  await expect(page.getByTestId("campus-profile-rename")).toHaveCount(0);
  await expect(page.getByTestId("campus-profile-item").first()).toHaveText("改过的名字");
  await expect(page.getByTestId("campus-profile-item")).toHaveCount(2);
});
