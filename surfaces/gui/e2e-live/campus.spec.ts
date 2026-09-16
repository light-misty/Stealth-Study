import { expect, test, type Page, type Response } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// LIVE campus integration — the real browser against a real `openworker-server`, no route mocks.
//
// This is the layer the hermetic suite in `e2e/` cannot provide: it catches the whole class of
// defect where the frontend calls an endpoint the backend does not answer (missing route, missing
// `profile_id`, wrong response shape). Every case also fails if ANY `/v1/campus/*` response comes
// back 4xx/5xx, so a silently-broken panel cannot hide behind an unrelated passing assertion.
//
// It needs a sidecar on 127.0.0.1:8765 (or `CAMPUS_LIVE_HTTP`) and no model key: every case here
// is deterministic and model-free, which is what makes it usable as a confidence smoke on a
// machine without cloud credentials. Run it with:
//   COWORKER_STATE_DIR=<state> npm run e2e:live -- campus.spec.ts
// and it skips itself when no live backend answers.

const HTTP = (process.env.CAMPUS_LIVE_HTTP ?? "http://127.0.0.1:8765").replace(/\/$/, "");

function liveToken(): string {
  const explicit = (process.env.CAMPUS_LIVE_TOKEN ?? "").trim();
  if (explicit) return explicit;
  const state =
    process.env.COWORKER_STATE_DIR ??
    (process.platform === "win32"
      ? path.join(process.env.APPDATA ?? os.homedir(), "coworker")
      : path.join(os.homedir(), ".config", "coworker"));
  const file = path.join(state, "sidecar-8765.token");
  return fs.existsSync(file) ? fs.readFileSync(file, "utf8").trim() : "";
}

const TOKEN = liveToken();
const auth = { "X-SS-Token": TOKEN };

/** Every `/v1/campus/*` response the page received that was not a success. */
function watchCampusCalls(page: Page): string[] {
  const failed: string[] = [];
  page.on("response", (response: Response) => {
    if (response.url().includes("/v1/campus") && response.status() >= 400) {
      failed.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });
  return failed;
}

async function installLiveBackend(page: Page): Promise<void> {
  // The dev server only bakes a token when IT booted with the same state dir, so the harness
  // injects the session the way the desktop shell does — `campus/api.ts` reads these globals first.
  await page.addInitScript(
    ({ http, token }) => {
      (window as unknown as Record<string, unknown>).__COWORKER_HTTP__ = http;
      (window as unknown as Record<string, unknown>).__COWORKER_API_TOKEN__ = token;
    },
    { http: HTTP, token: TOKEN },
  );
}

function uniqueTitle(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}`;
}

/** Open the guided create card, whether the station is empty or already has a profile. */
async function ensureCreateCard(page: Page): Promise<void> {
  const card = page.getByTestId("campus-profile-create-card");
  const switcherCreate = page.getByTestId("campus-profile-create");
  // Wait for the station to settle first: it boots through `campus-station-loading`, and poking at
  // a selector before either entry exists turns into a wait rather than a failure.
  await expect(card.or(switcherCreate).first()).toBeVisible();
  if ((await card.count()) > 0) return;
  await switcherCreate.click();
  await expect(card).toBeVisible();
}

/** Create a profile through the real UI and return its id (read back from the API). */
async function createProfile(page: Page, title: string): Promise<string> {
  await ensureCreateCard(page);
  await page.getByTestId("campus-profile-create-title").fill(title);
  await page.getByTestId("campus-profile-create-submit").click();
  await expect(page.getByTestId("campus-station")).toBeVisible();
  const response = await page.request.get(`${HTTP}/v1/campus/profiles`, { headers: auth });
  const body = (await response.json()) as { items: { id: string; title: string }[] };
  return body.items.find((row) => row.title === title)?.id ?? "";
}

async function dropProfile(page: Page, profileId: string): Promise<void> {
  if (profileId) {
    await page.request.delete(`${HTTP}/v1/campus/profiles/${profileId}`, { headers: auth });
  }
}

let live = false;
let liveNote = "";

test.describe("campus live integration (real backend, no mocks)", () => {
  test.beforeAll(async ({ request }) => {
    if (!TOKEN) {
      liveNote = "no sidecar token found (set CAMPUS_LIVE_TOKEN or COWORKER_STATE_DIR)";
      return;
    }
    try {
      const response = await request.get(`${HTTP}/v1/health`, { headers: auth, timeout: 5000 });
      live = response.ok();
      liveNote = live ? "" : `${HTTP}/v1/health answered ${response.status()}`;
    } catch (error) {
      liveNote = `${HTTP} unreachable: ${(error as Error).message}`;
    }
  });

  test.beforeEach(async ({ page }, testInfo) => {
    testInfo.skip(!live, `no live sidecar — ${liveNote}`);
    await installLiveBackend(page);
  });

  test("the CET station creates a real profile and renders its panels", async ({ page }) => {
    const failed = watchCampusCalls(page);
    const title = uniqueTitle("联调四级");

    await page.goto("/");
    await page.getByTestId("nav-campus-cet").click();
    // The state dir may already hold profiles, so the station is either empty or showing one —
    // both are valid entry points and the guided create card is reachable from either.
    await ensureCreateCard(page);

    const profileId = await createProfile(page, title);
    expect(profileId, "the created profile is readable through A1").not.toBe("");

    await expect(page.getByTestId("campus-station-header")).toBeVisible();
    await expect(page.getByTestId("campus-cet-assessment-start")).toBeVisible();
    await expect(page.getByTestId("campus-mock-start")).toBeVisible();
    // B/C/D panels are mounted on this track too — a missing backend route shows up below.
    await expect(page.getByTestId("campus-mistake-empty")).toBeVisible();
    await expect(page.getByTestId("campus-cet-common-errors")).toBeVisible();

    await dropProfile(page, profileId);
    expect(failed, "no campus request may fail").toEqual([]);
  });

  test("a real markdown upload is parsed and keeps its own filename", async ({ page }) => {
    const failed = watchCampusCalls(page);

    await page.goto("/");
    await page.getByTestId("nav-campus-kaoyan").click();
    const profileId = await createProfile(page, uniqueTitle("联调资料"));

    const filename = "考研英语真题.md";
    await page.getByTestId("campus-library-import").setInputFiles({
      name: filename,
      mimeType: "text/markdown",
      buffer: Buffer.from("# 第一章 阅读\n\n长难句的主干是主语加谓语加宾语。\n\n细节题先定位关键词。"),
    });
    await expect(page.getByTestId("campus-library-row")).toBeVisible();
    // B1 must name the document after the client's file, not after the server-side staging file.
    await expect(page.getByTestId("campus-library-title")).toContainText("考研英语真题");
    await expect(page.getByTestId("campus-library-status")).toContainText(/就绪|ready/i);

    await page.getByTestId("campus-library-delete").click();
    await expect(page.getByTestId("campus-library-row")).toHaveCount(0);

    await dropProfile(page, profileId);
    expect(failed, "no campus request may fail").toEqual([]);
  });

  test("the mock exam advances stage and locks the writing sheet (real locked_stages wire)", async ({
    page,
  }) => {
    const failed = watchCampusCalls(page);

    await page.goto("/");
    await page.getByTestId("nav-campus-cet").click();
    const profileId = await createProfile(page, uniqueTitle("联调模考"));

    await page.getByTestId("campus-mock-start").click();
    await expect(page.getByTestId("campus-mock-timer")).toBeVisible();
    await expect(page.getByTestId("campus-mock-stage")).toHaveAttribute("data-stage", "writing");

    // The dev-only fast-forward hook ends the writing window; F12 then locks the stage server-side.
    await page.getByTestId("fast-forward-hook").click();
    await page.getByTestId("campus-mock-advance").click();
    await expect(page.getByTestId("campus-mock-stage")).toHaveAttribute("data-stage", "listening");
    // The backend keeps `locked_stages` a JSON string; this line fails if the client stops decoding it.
    await expect(page.getByTestId("campus-mock-essay")).toBeDisabled();

    // F11 after a reload: a fresh boot lands on the session surface, so re-enter the station and
    // let the console resume from the stored exam — the server recomputes both the remaining
    // seconds and the stage lock from its own row.
    await page.reload();
    await page.getByTestId("nav-campus-cet").click();
    await expect(page.getByTestId("campus-mock-stage")).toHaveAttribute("data-stage", "listening");
    await expect(page.getByTestId("campus-mock-essay")).toBeDisabled();

    await dropProfile(page, profileId);
    expect(failed, "no campus request may fail").toEqual([]);
  });

  test("the knowledge tree, the mistake book and the persona list answer on the cert station", async ({
    page,
  }) => {
    const failed = watchCampusCalls(page);

    await page.goto("/");
    await page.getByTestId("nav-campus-cert").click();
    const profileId = await createProfile(page, uniqueTitle("联调教资"));

    // H2/H1: add a root point through the panel and read the tree back.
    await page.getByTestId("campus-cert-tree-add-root").click();
    await page.getByTestId("campus-cert-tree-add-title").fill("第一章 德育");
    await page.getByTestId("campus-cert-tree-add-submit").click();
    await expect(page.getByTestId("campus-cert-tree-node").first()).toBeVisible();
    await expect(page.getByTestId("campus-cert-tree-coverage")).toBeVisible();

    // D1/D3: the mistake book answers (empty is fine — it must not be a 404).
    await expect(page.getByTestId("campus-mistake-empty")).toBeVisible();

    // I1 has no panel yet, so the endpoint is exercised directly; the count is the six declared
    // personas and every entry carries the metadata the station would render.
    const personas = await page.request.get(`${HTTP}/v1/campus/personas`, { headers: auth });
    expect(personas.status()).toBe(200);
    const body = (await personas.json()) as { items: { id: string; name: string }[] };
    expect(body.items.map((row) => row.id)).toEqual([
      "cet-examiner",
      "cet-grader",
      "kaoyan-planner",
      "kaoyan-subject-tutor",
      "cert-instructor",
      "study-companion",
    ]);

    await dropProfile(page, profileId);
    expect(failed, "no campus request may fail").toEqual([]);
  });
});
