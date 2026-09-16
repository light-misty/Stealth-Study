import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../../campus/api";

vi.mock("../../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../campus/api")>();
  return { ...actual, getCommonErrors: vi.fn() };
});

import * as api from "../../../campus/api";
import { CommonErrorsCard } from "./CommonErrorsCard";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

describe("CommonErrorsCard", () => {
  beforeEach(() => {
    apiMock.getCommonErrors.mockReset();
  });

  it("lists the aggregated top mistakes with their counts", async () => {
    apiMock.getCommonErrors.mockResolvedValue({
      top3: [
        { type: "主谓一致", count: 7, samples: ["I thinks", "He go"] },
        { type: "时态", count: 4, samples: ["I will went"] },
      ],
    });
    render(<CommonErrorsCard profileId="p1" />);
    await waitFor(() => expect(screen.getAllByTestId("campus-cet-common-error")).toHaveLength(2));
    expect(screen.getAllByTestId("campus-cet-common-error")[0].getAttribute("data-type")).toBe(
      "主谓一致",
    );
    expect(screen.getAllByTestId("campus-cet-common-error")[0].textContent).toContain("7");
    expect(screen.getAllByTestId("campus-cet-common-error")[0].textContent).toContain("I thinks");
  });

  it("passes the kind filter through to the endpoint", async () => {
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
    render(<CommonErrorsCard profileId="p1" kind="essay" />);
    await waitFor(() => expect(screen.getByTestId("campus-cet-common-errors-empty")).toBeTruthy());
    expect(apiMock.getCommonErrors).toHaveBeenCalledWith("p1", "essay");
  });

  it("shows the empty state before the aggregation window is reached", async () => {
    apiMock.getCommonErrors.mockResolvedValue({ top3: [] });
    render(<CommonErrorsCard profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-cet-common-errors-empty")).toBeTruthy());
    expect(screen.queryByTestId("campus-cet-common-error")).toBeNull();
  });

  it("renders a retryable error state instead of silent nothing", async () => {
    apiMock.getCommonErrors.mockRejectedValue(
      new CampusApiError("UNKNOWN", "boom", true, 500),
    );
    render(<CommonErrorsCard profileId="p1" />);
    await waitFor(() => expect(screen.getByTestId("campus-cet-common-errors-error")).toBeTruthy());
    expect(screen.queryByTestId("campus-cet-common-error")).toBeNull();
  });

  it("does not render the card body until the profile is known", () => {
    render(<CommonErrorsCard profileId="" />);
    expect(screen.queryByTestId("campus-cet-common-error")).toBeNull();
    expect(apiMock.getCommonErrors).not.toHaveBeenCalled();
  });
});
