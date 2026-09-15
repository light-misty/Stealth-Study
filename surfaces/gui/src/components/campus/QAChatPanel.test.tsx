import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../campus/api";
import type { LibraryQAAnswer } from "../../campus/types";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return { ...actual, askLibrary: vi.fn() };
});

import * as api from "../../campus/api";
import { QAChatPanel } from "./QAChatPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const answer = (): LibraryQAAnswer => ({
  answer: "答案在第 3 页",
  citations: [
    { doc_id: "d1", page_no: 3, snippet: "…" },
    { doc_id: "d1", page_no: 7, snippet: "…" },
  ],
  used_retrieval: "keyword",
  chunks_used: 5,
});

const type = (value: string) =>
  fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value } });

describe("QAChatPanel", () => {
  beforeEach(() => {
    apiMock.askLibrary.mockReset();
    apiMock.askLibrary.mockResolvedValue(answer());
  });

  it("asks the library and renders the answer with its citations", async () => {
    render(<QAChatPanel profileId="p1" />);
    type("这一章讲了什么？");
    fireEvent.click(screen.getByTestId("campus-qa-send"));

    await waitFor(() => expect(screen.getByTestId("campus-qa-answer")).toBeTruthy());
    expect(apiMock.askLibrary).toHaveBeenCalledWith("p1", "这一章讲了什么？", undefined);
    expect(screen.getByTestId("campus-qa-answer").textContent).toContain("答案在第 3 页");
    expect(screen.getAllByTestId("campus-citation")).toHaveLength(2);
  });

  it("scopes the question to a document when one is selected", async () => {
    render(<QAChatPanel profileId="p1" docId="d1" />);
    type("?");
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    await waitFor(() => expect(apiMock.askLibrary).toHaveBeenCalledWith("p1", "?", "d1"));
  });

  it("jumps to a citation when it is clicked", async () => {
    const onCite = vi.fn();
    render(<QAChatPanel profileId="p1" onCite={onCite} />);
    type("?");
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    await waitFor(() => expect(screen.getAllByTestId("campus-citation")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-citation")[1]);
    expect(onCite).toHaveBeenCalledWith("d1", 7);
  });

  it("ignores a blank question instead of firing a request", () => {
    render(<QAChatPanel profileId="p1" />);
    type("   ");
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    expect(apiMock.askLibrary).not.toHaveBeenCalled();
  });

  it("shows the failure and keeps the previous answer cleared", async () => {
    apiMock.askLibrary.mockRejectedValue(new CampusApiError("DOC_NOT_READY", "busy", true, 409));
    render(<QAChatPanel profileId="p1" />);
    type("?");
    fireEvent.click(screen.getByTestId("campus-qa-send"));

    await waitFor(() => expect(screen.getByTestId("campus-qa-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-qa-answer")).toBeNull();
  });

  it("carries the AI disclaimer on the answer", async () => {
    render(<QAChatPanel profileId="p1" />);
    type("?");
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    await waitFor(() => expect(screen.getByTestId("campus-qa-answer")).toBeTruthy());
    expect(screen.getByTestId("campus-qa-notice").textContent).toBe(
      "AI generated, for reference only",
    );
  });
});
