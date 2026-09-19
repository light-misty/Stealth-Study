// Pausing a conversation that is waiting on a live ask_user prompt. The question card
// rendered in the composer head used to survive the Stop button — the interrupted turn
// left the question item unresolved, so the card stayed and any answer typed into it was
// silently dropped (the server had already cancelled the wait). The fix dismisses the
// pending question on interrupt; the ask itself stays in the session context (engine
// persists the tool call + "interrupted by user" result) so the conversation continues
// with full history afterwards.
import { expect } from "@playwright/test";
import { test, seedSessionMessages } from "./fixtures";

const QUESTION = "Which color should the report use?";
const TS = 1755600000;

// Mirrors the engine's persisted shape for an ask_user turn stopped by the user:
// the tool call (with the question), its "interrupted by user" result, the marker.
const PAUSED_QUESTION_HISTORY = [
  { role: "user", content: "help me pick a color", ts: TS },
  {
    role: "assistant",
    content: "",
    tool_calls: [
      {
        id: "tq1",
        function: {
          name: "ask_user",
          arguments: JSON.stringify({ question: QUESTION, options: ["Red", "Blue"] }),
        },
      },
    ],
  },
  { role: "tool", tool_call_id: "tq1", content: JSON.stringify({ answer: "", error: "interrupted by user" }) },
  { role: "notice", kind: "interrupted" },
];

async function askAndOpenSession(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByText("Draft the launch note").first().click();
  const box = page.getByPlaceholder(/Ask your study partner/);
  await box.fill("ask me something");
  await box.press("Enter");
  return box;
}

test("stopping the turn while the agent asks hides the question card immediately", async ({
  page,
}) => {
  await askAndOpenSession(page);

  const card = page.getByText(QUESTION);
  await expect(card).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: /Stop/ }).click();

  await expect(page.getByText("Interrupted.").first()).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(QUESTION)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Red", exact: true })).toHaveCount(0);
});

test("the conversation continues with full context after the pause", async ({ page }) => {
  const box = await askAndOpenSession(page);
  await expect(page.getByText(QUESTION)).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: /Stop/ }).click();
  await expect(page.getByText("Interrupted.").first()).toBeVisible({ timeout: 5_000 });

  await box.fill("continue please");
  await box.press("Enter");
  await expect(page.getByText("Echo: continue please", { exact: false }).first()).toBeVisible({
    timeout: 10_000,
  });
  await expect(page.getByText(QUESTION)).toHaveCount(0);
});

test("reopening the paused session replays the ask with its question text", async ({ page }) => {
  await seedSessionMessages(page, "pinned-cowork-1", PAUSED_QUESTION_HISTORY);
  await page.goto("/");
  await page.getByText("Draft the launch note").first().click();

  const group = page.locator(".stepgroup").first();
  await group.locator("summary").click();
  await expect(page.getByTestId("turn-step")).toHaveCount(1);
  await expect(
    page.getByText("Asked you a question — Which color should the report use?").first(),
  ).toBeVisible();
  await expect(page.getByText("Interrupted.")).toBeVisible();

  await expect(page.getByRole("button", { name: "Red", exact: true })).toHaveCount(0);
  await expect(page.getByTestId("question-skip")).toHaveCount(0);
});

test("pausing after a full Q&A round behaves the same", async ({ page }) => {
  const box = await askAndOpenSession(page);
  await expect(page.getByText(QUESTION)).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: "Red", exact: true }).click();
  await expect(page.getByText("Noted: Red").first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(QUESTION)).toHaveCount(0);

  await box.fill("ask me something");
  await box.press("Enter");
  await expect(page.getByText(QUESTION)).toBeVisible({ timeout: 10_000 });

  await page.getByRole("button", { name: /Stop/ }).click();
  await expect(page.getByText("Interrupted.").first()).toBeVisible({ timeout: 5_000 });
  await expect(page.getByText(QUESTION)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Blue", exact: true })).toHaveCount(0);
});
