import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../campus/api";
import type { ReviewDueItem } from "../../campus/types";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return { ...actual, listDueReviews: vi.fn(), submitReviewResult: vi.fn() };
});

import * as api from "../../campus/api";
import { ReviewQueuePanel } from "./ReviewQueuePanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const due = (id: string, streakRight = 0): ReviewDueItem => ({
  id,
  profile_id: "p1",
  item_type: "mistake",
  item_id: `m-${id}`,
  due_at: "2026-09-15T00:00:00Z",
  interval_days: 1,
  streak_right: streakRight,
  ease: 2.5,
  status: "pending",
  last_reviewed_at: null,
  created_at: "2026-09-01T00:00:00Z",
  payload: { word: `word-${id}` },
});

const rowIds = () =>
  screen.getAllByTestId("campus-review-item").map((el) => el.getAttribute("data-id"));

describe("ReviewQueuePanel", () => {
  beforeEach(() => {
    apiMock.listDueReviews.mockReset();
    apiMock.submitReviewResult.mockReset();
    apiMock.listDueReviews.mockResolvedValue({ items: [due("r1"), due("r2")] });
    apiMock.submitReviewResult.mockResolvedValue({ ...due("r1"), status: "done" });
  });

  it("lists what is due today", async () => {
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-review-item")).toHaveLength(2));
    expect(rowIds()).toEqual(["r1", "r2"]);
  });

  it("renders a caller-supplied queue without fetching", () => {
    render(<ReviewQueuePanel profileId="p1" dueItems={[due("x1")]} />);
    expect(rowIds()).toEqual(["x1"]);
    expect(apiMock.listDueReviews).not.toHaveBeenCalled();
  });

  it("submits a correct answer and drops the card (optimistic)", async () => {
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-review-item")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-review-correct")[0]);
    await waitFor(() => expect(apiMock.submitReviewResult).toHaveBeenCalledWith("p1", "r1", true));
    await waitFor(() => expect(rowIds()).toEqual(["r2"]));
  });

  it("submits a wrong answer the same way", async () => {
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-review-item")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-review-wrong")[1]);
    await waitFor(() => expect(apiMock.submitReviewResult).toHaveBeenCalledWith("p1", "r2", false));
    await waitFor(() => expect(rowIds()).toEqual(["r1"]));
  });

  it("shows an empty state when nothing is due", async () => {
    apiMock.listDueReviews.mockResolvedValue({ items: [] });
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-review-empty")).toBeTruthy());
    expect(screen.queryByTestId("campus-review-item")).toBeNull();
  });

  it("restores the card and reports the error when the write fails", async () => {
    apiMock.submitReviewResult.mockRejectedValue(
      new CampusApiError("RQ_NOT_FOUND", "gone", false, 404),
    );
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-review-item")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-review-correct")[0]);
    await waitFor(() => expect(screen.getByTestId("campus-review-error")).toBeTruthy());
    expect(rowIds()).toEqual(["r1", "r2"]);
  });

  it("previews the next interval from the SM-2 ladder", async () => {
    apiMock.listDueReviews.mockResolvedValue({ items: [due("r1", 2)] });
    render(<ReviewQueuePanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-review-item")).toHaveLength(1));
    // streak 2 + a correct answer → the 3rd rung of the 1/2/4/7/15 ladder.
    expect(screen.getByTestId("campus-review-interval").textContent).toContain("4");
  });
});
