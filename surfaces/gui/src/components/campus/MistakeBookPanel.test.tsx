import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MistakeBookEntry } from "../../campus/types";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return { ...actual, listMistakes: vi.fn(), patchMistake: vi.fn() };
});

import * as api from "../../campus/api";
import { MistakeBookPanel } from "./MistakeBookPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const mistake = (id: string, attribution = "pending"): MistakeBookEntry => ({
  id,
  profile_id: "p1",
  attempt_id: `a-${id}`,
  track_type: "cet",
  subject: "reading",
  question_id: null,
  point_id: null,
  attribution: attribution as MistakeBookEntry["attribution"],
  attribution_confidence: null,
  wrong_count: 2,
  last_wrong_at: "2026-09-10T08:00:00Z",
  resolved: 0,
  note: "",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
});

describe("MistakeBookPanel", () => {
  beforeEach(() => {
    apiMock.listMistakes.mockReset();
    apiMock.patchMistake.mockReset();
    apiMock.listMistakes.mockResolvedValue({ items: [mistake("m1"), mistake("m2")], total: 2 });
    apiMock.patchMistake.mockImplementation(
      (_profileId: string, id: string, patch: { attribution: string }) =>
        Promise.resolve(mistake(id, patch.attribution)),
    );
  });

  it("loads the mistake book for the active profile", async () => {
    render(<MistakeBookPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-mistake-row").length).toBe(2));
    expect(apiMock.listMistakes).toHaveBeenCalledWith("p1", {});
    expect(screen.getByTestId("campus-mistake-total").textContent).toContain("2");
  });

  it("shows the empty state instead of an empty list", async () => {
    apiMock.listMistakes.mockResolvedValue({ items: [], total: 0 });
    render(<MistakeBookPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-mistake-empty")).toBeTruthy());
    expect(screen.queryByTestId("campus-mistake-row")).toBeNull();
  });

  it("windows a long list instead of mounting every row", async () => {
    const many = Array.from({ length: 1000 }, (_, i) => mistake(`m${i}`));
    apiMock.listMistakes.mockResolvedValue({ items: many, total: 1000 });
    render(<MistakeBookPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-mistake-row").length).toBeGreaterThan(0));

    const mounted = screen.getAllByTestId("campus-mistake-row").length;
    expect(mounted).toBeLessThan(30);
    expect(screen.getByTestId("campus-mistake-total").textContent).toContain("1000");
    expect(screen.getByTestId("campus-mistake-window").textContent).toContain(String(mounted));
  });

  it("re-attributes a row through D2 and keeps the change", async () => {
    render(<MistakeBookPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-mistake-row").length).toBe(2));

    const select = screen.getAllByTestId("campus-mistake-attribution")[0] as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "misread" } });

    await waitFor(() => expect(apiMock.patchMistake).toHaveBeenCalledWith("p1", "m1", { attribution: "misread" }));
    await waitFor(() =>
      expect((screen.getAllByTestId("campus-mistake-attribution")[0] as HTMLSelectElement).value).toBe(
        "misread",
      ),
    );
  });

  it("surfaces a failed re-attribution without losing the row", async () => {
    apiMock.patchMistake.mockRejectedValue(new Error("offline"));
    render(<MistakeBookPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-mistake-row").length).toBe(2));

    fireEvent.change(screen.getAllByTestId("campus-mistake-attribution")[0], {
      target: { value: "misread" },
    });
    await waitFor(() => expect(screen.getByTestId("campus-mistake-error")).toBeTruthy());
    expect(screen.getAllByTestId("campus-mistake-row")).toHaveLength(2);
  });
});
