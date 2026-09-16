import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LibraryQAAnswer, SourceDoc } from "../../../campus/types";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return { ...actual, askLibrary: vi.fn(), listLibraryDocs: vi.fn() };
});

import * as api from "../../../campus/api";
import { MajorQAView } from "./MajorQAView";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const doc = (id: string, title: string): SourceDoc => ({
  id,
  profile_id: "p1",
  title,
  file_path: `/tmp/${id}.pdf`,
  file_type: "pdf",
  page_count: 10,
  parse_status: "ready",
  fail_reason: null,
  chunk_count: 5,
  char_count: 1200,
  imported_at: "2026-09-01T00:00:00Z",
});

const answer: LibraryQAAnswer = {
  answer: "The answer lives in chapter two.",
  citations: [
    { doc_id: "doc-1", page_no: 3, snippet: "..." },
    { doc_id: "doc-2", page_no: 7, snippet: "..." },
  ],
  used_retrieval: "keyword",
  chunks_used: 2,
};

beforeEach(() => {
  apiMock.askLibrary.mockReset();
  apiMock.listLibraryDocs.mockReset();
  apiMock.listLibraryDocs.mockResolvedValue({ items: [doc("doc-1", "Polynomials"), doc("doc-2", "Linear Algebra")] });
});

describe("MajorQAView", () => {
  it("lists the profile documents with an all-documents default", async () => {
    render(<MajorQAView profileId="p1" />);

    const select = (await waitFor(() => screen.getByTestId("campus-major-qa-doc"))) as HTMLSelectElement;
    expect(select.options).toHaveLength(3);
    expect(select.value).toBe("");
    expect(select.options[1].textContent).toContain("Polynomials");
  });

  it("asks with the picked doc id once a document is selected", async () => {
    apiMock.askLibrary.mockResolvedValue(answer);
    render(<MajorQAView profileId="p1" />);

    const select = (await waitFor(() => screen.getByTestId("campus-major-qa-doc"))) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "doc-2" } });
    fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value: "What is a vector space?" } });
    fireEvent.click(screen.getByTestId("campus-qa-send"));

    await waitFor(() => expect(screen.getByTestId("campus-qa-answer")).toBeTruthy());
    expect(apiMock.askLibrary).toHaveBeenCalledWith("p1", "What is a vector space?", "doc-2");
  });

  it("asks across all documents when nothing is picked", async () => {
    apiMock.askLibrary.mockResolvedValue(answer);
    render(<MajorQAView profileId="p1" />);

    await waitFor(() => screen.getByTestId("campus-major-qa-doc"));
    fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value: "Give me the syllabus" } });
    fireEvent.click(screen.getByTestId("campus-qa-send"));

    await waitFor(() => expect(apiMock.askLibrary).toHaveBeenCalled());
    expect(apiMock.askLibrary).toHaveBeenCalledWith("p1", "Give me the syllabus", undefined);
  });

  it("renders clickable page citations and reports the picked one", async () => {
    apiMock.askLibrary.mockResolvedValue(answer);
    const onCite = vi.fn();
    render(<MajorQAView profileId="p1" onCite={onCite} />);

    await waitFor(() => screen.getByTestId("campus-major-qa-doc"));
    fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value: "q" } });
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    await waitFor(() => expect(screen.getAllByTestId("campus-citation")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-citation")[0]);
    expect(onCite).toHaveBeenCalledWith("doc-1", 3);
  });

  it("disables sending while a question is in flight", async () => {
    let release: (value: LibraryQAAnswer) => void = () => {};
    apiMock.askLibrary.mockReturnValue(
      new Promise<LibraryQAAnswer>((resolve) => {
        release = resolve;
      }),
    );
    render(<MajorQAView profileId="p1" />);

    await waitFor(() => screen.getByTestId("campus-major-qa-doc"));
    fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value: "q" } });
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    expect((screen.getByTestId("campus-qa-send") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("campus-qa-send"));
    expect(apiMock.askLibrary).toHaveBeenCalledTimes(1);

    release(answer);
    await waitFor(() =>
      expect((screen.getByTestId("campus-qa-send") as HTMLButtonElement).disabled).toBe(false),
    );
  });

  it("shows the ask error when the backend rejects", async () => {
    apiMock.askLibrary.mockRejectedValue(new Error("no retrieval"));
    render(<MajorQAView profileId="p1" />);

    await waitFor(() => screen.getByTestId("campus-major-qa-doc"));
    fireEvent.change(screen.getByTestId("campus-qa-input"), { target: { value: "q" } });
    fireEvent.click(screen.getByTestId("campus-qa-send"));

    await waitFor(() => expect(screen.getByTestId("campus-qa-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-qa-answer")).toBeNull();
  });
});
