import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CampusApiError } from "../../campus/api";
import type { ExamProfile } from "../../campus/types";
import { CampusProfileProvider, useCampusProfile } from "./CampusProfileContext";

vi.mock("../../campus/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../campus/api")>();
  return {
    ...actual,
    listProfiles: vi.fn(),
    getAppState: vi.fn(),
    patchAppState: vi.fn(),
    createProfile: vi.fn(),
    patchProfile: vi.fn(),
  };
});

import * as api from "../../campus/api";
import { campusErrorInfo } from "../../campus/utils";

const apiMock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;

afterEach(cleanup);

const profile = (id: string): ExamProfile => ({
  id,
  track_type: "cet",
  title: `档案-${id}`,
  cert_type: null,
  level: "cet4",
  exam_date: "2026-12-19",
  target_score: 500,
  current_estimate: 420,
  subjects: ["reading"],
  daily_minutes: 60,
  status: "active",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  archived_at: null,
});

function Probe() {
  const {
    profiles,
    activeProfile,
    loading,
    error,
    actionError,
    setActive,
    createProfile,
    setStatus,
  } = useCampusProfile();
  return (
    <div>
      <span data-testid="profiles">{profiles.map((p) => p.id).join(",")}</span>
      <span data-testid="active">{activeProfile?.id ?? "none"}</span>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ? "err" : "ok"}</span>
      <span data-testid="action-error">
        {actionError ? `${actionError.action}:${campusErrorInfo(actionError.error).code}` : "none"}
      </span>
      <span data-testid="action-title">{actionError?.title ?? "none"}</span>
      <button data-testid="switch" onClick={() => void setActive("p2")} />
      <button data-testid="archive" onClick={() => void setStatus("p1", "archived")} />
      <button
        data-testid="create"
        onClick={() => void createProfile({ track_type: "cet", title: "新档案" })}
      />
    </div>
  );
}

describe("CampusProfileProvider", () => {
  beforeEach(() => {
    for (const fn of Object.values(apiMock)) if (typeof fn?.mockReset === "function") fn.mockReset();
    apiMock.listProfiles.mockResolvedValue({ items: [profile("p1"), profile("p2")] });
    apiMock.getAppState.mockResolvedValue({ active_profile_id: "p1", settings: {} });
    apiMock.patchAppState.mockResolvedValue({ active_profile_id: "p2", settings: {} });
  });

  it("publishes the profile list and the remembered active profile", async () => {
    render(
      <CampusProfileProvider track="cet">
        <Probe />
      </CampusProfileProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("profiles").textContent).toBe("p1,p2");
    expect(screen.getByTestId("active").textContent).toBe("p1");
    expect(apiMock.listProfiles).toHaveBeenCalledWith("cet");
  });

  it("activates a profile through app state and refreshes it in context", async () => {
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByTestId("switch").click();
    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("p2"));
    expect(apiMock.patchAppState).toHaveBeenCalledWith({ active_profile_id: "p2" });
  });

  it("creates a profile, adopts it as active and reloads the list", async () => {
    apiMock.createProfile.mockResolvedValue(profile("p3"));
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByTestId("create").click();
    await waitFor(() => expect(apiMock.createProfile).toHaveBeenCalled());
    expect(apiMock.createProfile).toHaveBeenCalledWith({ track_type: "cet", title: "新档案" });
    await waitFor(() => expect(apiMock.patchAppState).toHaveBeenCalledWith({ active_profile_id: "p3" }));
    // reload() re-issues A1 after the create.
    await waitFor(() => expect(apiMock.listProfiles.mock.calls.length).toBeGreaterThan(1));
  });

  it("surfaces a load failure instead of silently showing an empty station", async () => {
    apiMock.listProfiles.mockRejectedValue(new CampusApiError("MODEL_TIMEOUT", "t", true, 504));
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("error").textContent).toBe("err"));
  });

  it("keeps a failed create out of the page-level error and names the profile it tried", async () => {
    apiMock.createProfile.mockRejectedValue(
      new CampusApiError("DUPLICATE_TITLE", "同名档案已存在：新档案", false, 409),
    );
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByTestId("create").click();

    await waitFor(() =>
      expect(screen.getByTestId("action-error").textContent).toBe("create:DUPLICATE_TITLE"),
    );
    expect(screen.getByTestId("action-title").textContent).toBe("新档案");
    expect(screen.getByTestId("error").textContent).toBe("ok");
  });

  it("changes a profile status through A4 and reloads the list", async () => {
    apiMock.patchProfile.mockResolvedValue(profile("p1"));
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByTestId("archive").click();

    await waitFor(() => expect(apiMock.patchProfile).toHaveBeenCalledWith("p1", { status: "archived" }));
    await waitFor(() => expect(apiMock.listProfiles.mock.calls.length).toBeGreaterThan(1));
    expect(screen.getByTestId("action-error").textContent).toBe("none");
  });

  it("reports a refused status change as an action error", async () => {
    apiMock.patchProfile.mockRejectedValue(
      new CampusApiError("PROFILE_READ_ONLY", "档案已结课，拒绝写入", false, 409),
    );
    render(
      <CampusProfileProvider>
        <Probe />
      </CampusProfileProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));

    screen.getByTestId("archive").click();

    await waitFor(() =>
      expect(screen.getByTestId("action-error").textContent).toBe("archive:PROFILE_READ_ONLY"),
    );
    expect(screen.getByTestId("error").textContent).toBe("ok");
  });
});

describe("useCampusProfile", () => {
  it("fails loudly when used outside the provider", () => {
    expect(() => render(<Probe />)).toThrow(/CampusProfileProvider/);
  });
});
