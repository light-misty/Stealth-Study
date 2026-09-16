import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MasteryLevel, VocabItem } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return {
    ...actual,
    listVocabToday: vi.fn(),
    setVocabMastery: vi.fn(),
    makeMnemonic: vi.fn(),
  };
});

import * as api from "../../../campus/api";
import { VocabPanel } from "./VocabPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const vocabItem = (id: string, word: string, mastery: MasteryLevel = "unknown"): VocabItem => ({
  id,
  profile_id: "p1",
  word,
  phonetic: "/t%C9%9Bst/",
  meaning: `meaning of ${word}`,
  example: `an example for ${word}`,
  example_source: "past_paper",
  freq_rank: null,
  mastery,
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
});

const today = () => ({
  new_items: [vocabItem("v1", "abundant"), vocabItem("v2", "thrive", "fuzzy")],
  review_items: [vocabItem("v3", "diligent", "mastered")],
});

describe("VocabPanel", () => {
  beforeEach(() => {
    apiMock.listVocabToday.mockReset();
    apiMock.setVocabMastery.mockReset();
    apiMock.makeMnemonic.mockReset();
  });

  it("renders the new and review sections with word details", async () => {
    apiMock.listVocabToday.mockResolvedValue(today());
    render(<VocabPanel profileId="p1" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
    expect(screen.getByTestId("campus-cet-vocab-section-new").textContent).toContain("abundant");
    expect(screen.getByTestId("campus-cet-vocab-section-review").textContent).toContain(
      "diligent",
    );
    expect(apiMock.listVocabToday).toHaveBeenCalledWith("p1");
  });

  it("shows the empty state when nothing is due", async () => {
    apiMock.listVocabToday.mockResolvedValue({ new_items: [], review_items: [] });
    render(<VocabPanel profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-vocab-empty")).toBeTruthy());
  });

  it("reports load failures and recovers through retry", async () => {
    apiMock.listVocabToday.mockRejectedValueOnce(new Error("down"));
    apiMock.listVocabToday.mockResolvedValue(today());
    render(<VocabPanel profileId="p1" />);

    await waitFor(() => expect(screen.getByTestId("campus-cet-vocab-error")).toBeTruthy());
    fireEvent.click(screen.getByTestId("campus-cet-vocab-retry"));
    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
  });

  it("marks mastery optimistically and calls the backend with the profile guard", async () => {
    apiMock.listVocabToday.mockResolvedValue(today());
    apiMock.setVocabMastery.mockImplementation((_vid: string, _pid: string, m: MasteryLevel) =>
      Promise.resolve(vocabItem("v1", "abundant", m)),
    );
    render(<VocabPanel profileId="p1" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
    fireEvent.click(screen.getAllByTestId("campus-cet-vocab-mastery").find(
      (el) => el.getAttribute("data-vocab") === "v1" && el.getAttribute("data-level") === "mastered",
    )!);
    await waitFor(() =>
      expect(apiMock.setVocabMastery).toHaveBeenCalledWith("v1", "p1", "mastered"),
    );
    const active = screen
      .getAllByTestId("campus-cet-vocab-mastery")
      .find(
        (el) =>
          el.getAttribute("data-vocab") === "v1" &&
          el.getAttribute("data-active") === "true" &&
          el.getAttribute("data-level") === "mastered",
      );
    expect(active).toBeTruthy();
  });

  it("rolls the mastery mark back when the backend rejects it", async () => {
    apiMock.listVocabToday.mockResolvedValue(today());
    apiMock.setVocabMastery.mockRejectedValue(new Error("down"));
    render(<VocabPanel profileId="p1" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
    fireEvent.click(screen.getAllByTestId("campus-cet-vocab-mastery").find(
      (el) => el.getAttribute("data-vocab") === "v1" && el.getAttribute("data-level") === "mastered",
    )!);
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-vocab-mastery-error")).toBeTruthy(),
    );
    const active = screen
      .getAllByTestId("campus-cet-vocab-mastery")
      .find(
        (el) =>
          el.getAttribute("data-vocab") === "v1" &&
          el.getAttribute("data-active") === "true" &&
          el.getAttribute("data-level") === "unknown",
      );
    expect(active).toBeTruthy();
  });

  it("generates a mnemonic and disables the button while it is pending", async () => {
    apiMock.listVocabToday.mockResolvedValue(today());
    let resolveMnemonic: (v: { mnemonic: string }) => void = () => {};
    apiMock.makeMnemonic.mockReturnValue(
      new Promise<{ mnemonic: string }>((resolve) => {
        resolveMnemonic = resolve;
      }),
    );
    render(<VocabPanel profileId="p1" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
    fireEvent.click(screen.getAllByTestId("campus-cet-vocab-mnemonic").find(
      (el) => el.getAttribute("data-vocab") === "v1",
    )!);
    expect(apiMock.makeMnemonic).toHaveBeenCalledWith("v1");
    const busy = screen
      .getAllByTestId("campus-cet-vocab-mnemonic")
      .find((el) => el.getAttribute("data-vocab") === "v1") as HTMLButtonElement;
    expect(busy.disabled).toBe(true);

    resolveMnemonic({ mnemonic: "A bear ate plenty of ants." });
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-vocab-mnemonic-text").textContent).toContain(
        "A bear ate plenty of ants.",
      ),
    );
    expect(
      (screen.getAllByTestId("campus-cet-vocab-mnemonic").find(
        (el) => el.getAttribute("data-vocab") === "v1",
      ) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("keeps the mnemonic button usable after a failure", async () => {
    apiMock.listVocabToday.mockResolvedValue(today());
    apiMock.makeMnemonic.mockRejectedValue(new Error("down"));
    render(<VocabPanel profileId="p1" />);

    await waitFor(() =>
      expect(screen.getAllByTestId("campus-cet-vocab-item")).toHaveLength(3),
    );
    fireEvent.click(screen.getAllByTestId("campus-cet-vocab-mnemonic").find(
      (el) => el.getAttribute("data-vocab") === "v1",
    )!);
    await waitFor(() =>
      expect(screen.getByTestId("campus-cet-vocab-mnemonic-error")).toBeTruthy(),
    );
    const button = screen
      .getAllByTestId("campus-cet-vocab-mnemonic")
      .find((el) => el.getAttribute("data-vocab") === "v1") as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });
});
