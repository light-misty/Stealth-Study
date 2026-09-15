import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SourceDoc } from "../../campus/types";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return {
    ...actual,
    listLibraryDocs: vi.fn(),
    importLibraryDoc: vi.fn(),
    getLibraryDoc: vi.fn(),
    retryLibraryDoc: vi.fn(),
    deleteLibraryDoc: vi.fn(),
  };
});

import * as api from "../../campus/api";
import { LibraryPanel } from "./LibraryPanel";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const doc = (id: string, parseStatus: SourceDoc["parse_status"] = "ready"): SourceDoc => ({
  id,
  profile_id: "p1",
  title: `${id}.pdf`,
  file_path: `/tmp/${id}.pdf`,
  file_type: "pdf",
  page_count: 12,
  parse_status: parseStatus,
  fail_reason: parseStatus === "failed" ? "no_text_layer" : null,
  chunk_count: 4,
  char_count: 1200,
  imported_at: "2026-09-01T00:00:00Z",
});

const rowIds = () =>
  screen.getAllByTestId("campus-library-row").map((el) => el.getAttribute("data-id"));

describe("LibraryPanel", () => {
  beforeEach(() => {
    for (const key of ["listLibraryDocs", "importLibraryDoc", "getLibraryDoc", "retryLibraryDoc", "deleteLibraryDoc"]) {
      apiMock[key].mockReset();
    }
    apiMock.listLibraryDocs.mockResolvedValue({ items: [doc("d1"), doc("d2", "pending")] });
    apiMock.deleteLibraryDoc.mockResolvedValue({ deleted: true });
    apiMock.retryLibraryDoc.mockResolvedValue(doc("d1", "ready"));
  });

  it("lists the imported docs with their parse state", async () => {
    render(<LibraryPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-library-row")).toHaveLength(2));
    const rows = screen.getAllByTestId("campus-library-row");
    expect(rows.map((r) => r.getAttribute("data-parse-status"))).toEqual(["ready", "pending"]);
    expect(rows[0].textContent).toContain("d1.pdf");
  });

  it("imports a file through B1 and shows it in the list", async () => {
    apiMock.importLibraryDoc.mockResolvedValue(doc("d3"));
    render(<LibraryPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-library-row")).toHaveLength(2));

    const input = screen.getByTestId("campus-library-import") as HTMLInputElement;
    const file = new File(["x"], "d3.pdf", { type: "application/pdf" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(apiMock.importLibraryDoc).toHaveBeenCalled());
    await waitFor(() => expect(rowIds()).toEqual(["d1", "d2", "d3"]));
  });

  it("offers a re-parse for a failed document", async () => {
    apiMock.listLibraryDocs.mockResolvedValue({ items: [doc("d1", "failed")] });
    render(<LibraryPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-library-row")).toBeTruthy());

    fireEvent.click(screen.getByTestId("campus-library-retry"));
    await waitFor(() => expect(apiMock.retryLibraryDoc).toHaveBeenCalledWith("d1"));
    await waitFor(() =>
      expect(screen.getByTestId("campus-library-row").getAttribute("data-parse-status")).toBe("ready"),
    );
  });

  it("deletes a document and drops it from the list", async () => {
    render(<LibraryPanel profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-library-row")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-library-delete")[0]);
    await waitFor(() => expect(rowIds()).toEqual(["d2"]));
  });

  it("shows the empty state before anything is imported", async () => {
    apiMock.listLibraryDocs.mockResolvedValue({ items: [] });
    render(<LibraryPanel profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-library-empty")).toBeTruthy());
  });

  it("reports the selected document upward when a title is clicked", async () => {
    const onSelectDoc = vi.fn();
    render(<LibraryPanel profileId="p1" onSelectDoc={onSelectDoc} />);
    await waitFor(() => expect(screen.getAllByTestId("campus-library-row")).toHaveLength(2));

    fireEvent.click(screen.getAllByTestId("campus-library-title")[1]);
    expect(onSelectDoc).toHaveBeenCalledWith("d2");
  });
});
