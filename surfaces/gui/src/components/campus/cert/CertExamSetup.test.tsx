import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";
import type { CertDeadline } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    listDeadlines: vi.fn(),
    createDeadline: vi.fn(),
    createDeadlineReminders: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { CertExamSetup } from "./CertExamSetup";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const item = (id: string, over: Partial<CertDeadline & { days_left: number }> = {}) => ({
  id,
  profile_id: "p1",
  node_type: "exam" as const,
  date: "2026-12-20",
  is_reference: 0,
  automation_ids: [] as string[],
  note: "",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  days_left: 10,
  ...over,
});

const nodeOf = (id: string) => {
  const row = screen
    .getAllByTestId("campus-cert-setup-node")
    .find((el) => el.getAttribute("data-id") === id);
  if (!row) throw new Error(`node ${id} not found`);
  return row;
};

describe("CertExamSetup", () => {
  beforeEach(() => {
    for (const key of ["listDeadlines", "createDeadline", "createDeadlineReminders"]) {
      apiMock[key].mockReset();
    }
    apiMock.listDeadlines.mockResolvedValue({ items: [item("d1"), item("d2", { days_left: 5 })] });
  });

  it("offers the six node types in the create form", () => {
    render(<CertExamSetup profileId="p1" />);
    const select = screen.getByTestId("campus-cert-setup-type") as HTMLSelectElement;
    expect(select.options).toHaveLength(6);
    expect(select.value).toBe("registration_open");
  });

  it("creates a node through H7 and refreshes the timeline", async () => {
    apiMock.listDeadlines.mockReset();
    apiMock.listDeadlines
      .mockResolvedValueOnce({ items: [item("d1")] })
      .mockResolvedValueOnce({ items: [item("d1"), item("d9", { node_type: "score_query" })] });
    apiMock.createDeadline.mockResolvedValue(item("d9", { node_type: "score_query" }));
    render(<CertExamSetup profileId="p1" />);
    await waitFor(() => expect(nodeOf("d1")).toBeTruthy());

    fireEvent.change(screen.getByTestId("campus-cert-setup-type"), {
      target: { value: "score_query" },
    });
    fireEvent.change(screen.getByTestId("campus-cert-setup-date"), {
      target: { value: "2027-02-10" },
    });
    fireEvent.click(screen.getByTestId("campus-cert-setup-create"));

    await waitFor(() =>
      expect(apiMock.createDeadline).toHaveBeenCalledWith({
        profileId: "p1",
        nodeType: "score_query",
        date: "2027-02-10",
        isReference: undefined,
      }),
    );
    await waitFor(() => expect(apiMock.listDeadlines).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(nodeOf("d9").getAttribute("data-type")).toBe("score_query"));
  });

  it("shows the DUPLICATE_NODE error and keeps the form when H7 refuses", async () => {
    apiMock.createDeadline.mockRejectedValue(
      new CampusApiError("DUPLICATE_NODE", "dup", false, 409),
    );
    render(<CertExamSetup profileId="p1" />);
    await waitFor(() => expect(nodeOf("d1")).toBeTruthy());

    fireEvent.change(screen.getByTestId("campus-cert-setup-date"), {
      target: { value: "2026-12-20" },
    });
    fireEvent.click(screen.getByTestId("campus-cert-setup-create"));

    await waitFor(() => expect(screen.getByTestId("campus-cert-setup-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-cert-setup-retry")).toBeNull();
    expect((screen.getByTestId("campus-cert-setup-date") as HTMLInputElement).value).toBe(
      "2026-12-20",
    );
  });

  it("rejects a missing date without calling H7", async () => {
    render(<CertExamSetup profileId="p1" />);
    await waitFor(() => expect(nodeOf("d1")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-cert-setup-create"));

    expect(apiMock.createDeadline).not.toHaveBeenCalled();
    expect(screen.getByTestId("campus-cert-setup-error")).toBeTruthy();
  });

  it("shows the timeline with labels, dates and deadline tiers", async () => {
    apiMock.listDeadlines.mockResolvedValue({
      items: [
        item("d1", { days_left: 35 }),
        item("d2", { days_left: 5, node_type: "payment_close" }),
        item("d3", { days_left: 1, node_type: "admission_ticket" }),
      ],
    });
    render(<CertExamSetup profileId="p1" />);

    await waitFor(() => expect(nodeOf("d3")).toBeTruthy());
    expect(nodeOf("d1").getAttribute("data-tier")).toBe("normal");
    expect(nodeOf("d1").getAttribute("data-days")).toBe("35");
    expect(nodeOf("d2").getAttribute("data-tier")).toBe("d7");
    expect(nodeOf("d3").getAttribute("data-tier")).toBe("d1");
    expect(within(nodeOf("d3")).getByText("2026-12-20")).toBeTruthy();
  });

  it("creates one-shot reminders through H9", async () => {
    apiMock.createDeadlineReminders.mockResolvedValue({ automation_ids: ["au1", "au2"] });
    render(<CertExamSetup profileId="p1" />);
    await waitFor(() => expect(nodeOf("d1")).toBeTruthy());

    fireEvent.click(within(nodeOf("d1")).getByTestId("campus-cert-setup-remind"));

    await waitFor(() => expect(apiMock.createDeadlineReminders).toHaveBeenCalledWith("p1", "d1"));
    await waitFor(() =>
      expect(within(nodeOf("d1")).queryByTestId("campus-cert-setup-remind")).toBeNull(),
    );
    expect(within(nodeOf("d1")).getByTestId("campus-cert-setup-reminders")).toBeTruthy();
  });

  it("shows the reminder state without the action when reminders exist", async () => {
    apiMock.listDeadlines.mockResolvedValue({
      items: [item("d1", { automation_ids: ["au1"] })],
    });
    render(<CertExamSetup profileId="p1" />);

    await waitFor(() => expect(nodeOf("d1")).toBeTruthy());
    expect(within(nodeOf("d1")).queryByTestId("campus-cert-setup-remind")).toBeNull();
    expect(within(nodeOf("d1")).getByTestId("campus-cert-setup-reminders")).toBeTruthy();
  });

  it("shows the empty state when no nodes exist", async () => {
    apiMock.listDeadlines.mockResolvedValue({ items: [] });
    render(<CertExamSetup profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cert-setup-empty")).toBeTruthy());
  });

  it("shows the load error with a retry", async () => {
    apiMock.listDeadlines.mockRejectedValue(
      new CampusApiError("MODEL_TIMEOUT", "timed out", true, 504),
    );
    render(<CertExamSetup profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cert-setup-error")).toBeTruthy());
    expect(screen.getByTestId("campus-cert-setup-retry")).toBeTruthy();
  });
});
