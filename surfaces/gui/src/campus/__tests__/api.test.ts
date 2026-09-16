import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { CampusApiError, exportDownloadUrl, importLibraryDoc } from "../api";
import * as api from "../api";

interface CapturedCall {
  url: string;
  init: RequestInit;
}

const realFetch = globalThis.fetch;
const realToken = (globalThis as { __COWORKER_API_TOKEN__?: string }).__COWORKER_API_TOKEN__;

function installFetch(status = 200, body: unknown = {}): CapturedCall[] {
  const calls: CapturedCall[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init: init ?? {} });
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => body,
    } as Response;
  }) as typeof fetch;
  return calls;
}

function headersOf(call: CapturedCall): Headers {
  return new Headers(call.init.headers);
}

beforeEach(() => {
  (globalThis as { __COWORKER_API_TOKEN__?: string }).__COWORKER_API_TOKEN__ = "tok-123";
  delete (globalThis as { __COWORKER_HTTP__?: string }).__COWORKER_HTTP__;
});

afterEach(() => {
  globalThis.fetch = realFetch;
  if (realToken === undefined) {
    delete (globalThis as { __COWORKER_API_TOKEN__?: string }).__COWORKER_API_TOKEN__;
  } else {
    (globalThis as { __COWORKER_API_TOKEN__?: string }).__COWORKER_API_TOKEN__ = realToken;
  }
});

describe("campus api transport", () => {
  it("sends the sidecar token header against the default dev base URL", async () => {
    const calls = installFetch(200, { items: [] });
    await api.listProfiles();
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/profiles");
    expect(headersOf(calls[0]).get("X-SS-Token")).toBe("tok-123");
  });

  it("omits the token header when no token is configured", async () => {
    delete (globalThis as { __COWORKER_API_TOKEN__?: string }).__COWORKER_API_TOKEN__;
    const calls = installFetch();
    await api.getAppState();
    expect(headersOf(calls[0]).get("X-SS-Token")).toBeNull();
  });

  it("encodes list filters into the query string and skips empty ones", async () => {
    const calls = installFetch();
    await api.listProfiles("cet", "active");
    await api.listMistakes("p1", { page: 2, pageSize: 25, attribution: "misread" });
    await api.listQuestions("p1");
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/profiles?track=cet&status=active");
    expect(calls[1].url).toContain("/v1/campus/mistakes?");
    expect(calls[1].url).toContain("profile_id=p1");
    expect(calls[1].url).toContain("attribution=misread");
    expect(calls[1].url).toContain("page=2");
    expect(calls[1].url).toContain("page_size=25");
    expect(calls[2].url).toBe("http://127.0.0.1:8765/v1/campus/questions?profile_id=p1");
  });

  it("posts JSON bodies with the application content type", async () => {
    const calls = installFetch(201, { id: "p1", track_type: "cet", title: "四级" });
    const created = await api.createProfile({ track_type: "cet", title: "四级" }, "idem-1");
    expect(created.id).toBe("p1");
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ track_type: "cet", title: "四级" });
    expect(headersOf(calls[0]).get("Content-Type")).toBe("application/json");
    expect(headersOf(calls[0]).get("Idempotency-Key")).toBe("idem-1");
  });

  it("patches and deletes by resource id", async () => {
    const calls = installFetch(200, { id: "p1" });
    await api.patchProfile("p1", { status: "archived" });
    await api.deleteProfile("p1");
    expect(calls[0].init.method).toBe("PATCH");
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/profiles/p1");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ status: "archived" });
    expect(calls[1].init.method).toBe("DELETE");
    expect(calls[1].url).toBe("http://127.0.0.1:8765/v1/campus/profiles/p1");
  });

  it("submits grading with snake_case payload fields", async () => {
    const calls = installFetch(200, { attempt_id: "a1", degrade_level: 0 });
    await api.submitGrading({
      profileId: "p1",
      kind: "essay",
      answer: "My essay",
      rubricId: "cet-essay",
    });
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/grading");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      profile_id: "p1",
      kind: "essay",
      answer: "My essay",
      rubric_id: "cet-essay",
    });
  });

  it("uploads library files as multipart without forcing a content type", async () => {
    const calls = installFetch(200, { id: "d1" });
    const file = new File(["pdf-bytes"], "讲义.pdf", { type: "application/pdf" });
    const doc = await importLibraryDoc("p1", file);
    expect(doc.id).toBe("d1");
    const form = calls[0].init.body as FormData;
    expect(form).toBeInstanceOf(FormData);
    expect(form.get("profile_id")).toBe("p1");
    expect(form.get("file")).toBeInstanceOf(File);
    expect(headersOf(calls[0]).get("Content-Type")).toBeNull();
  });

  it("unwraps structured campus errors into CampusApiError", async () => {
    installFetch(409, {
      detail: { code: "DUPLICATE_TITLE", message: "档案重名", retryable: false },
    });
    const err = await api.createProfile({ track_type: "cet", title: "四级" }).then(
      () => null,
      (e: unknown) => e,
    );
    expect(err).toBeInstanceOf(CampusApiError);
    const campusErr = err as CampusApiError;
    expect(campusErr.code).toBe("DUPLICATE_TITLE");
    expect(campusErr.message).toBe("档案重名");
    expect(campusErr.retryable).toBe(false);
    expect(campusErr.status).toBe(409);
    expect(campusErr.name).toBe("CampusApiError");
  });

  it("falls back to UNKNOWN with status-derived retryable for string details", async () => {
    installFetch(500, { detail: "boom" });
    const err = await api.getAppState().then(
      () => null,
      (e: unknown) => e,
    );
    const campusErr = err as CampusApiError;
    expect(campusErr).toBeInstanceOf(CampusApiError);
    expect(campusErr.code).toBe("UNKNOWN");
    expect(campusErr.retryable).toBe(true);
    expect(campusErr.status).toBe(500);
  });

  it("maps 204 responses to null", async () => {
    installFetch(204);
    const result = await api.deleteLibraryDoc("d1");
    expect(result).toBeNull();
  });

  it("builds the export download URL from the same base", () => {
    expect(exportDownloadUrl("profile-p1.md")).toBe(
      "http://127.0.0.1:8765/v1/campus/exports/profile-p1.md",
    );
  });

  it("keeps the vocab mastery contract on the backend three-level enum", async () => {
    const calls = installFetch(200, { id: "v1" });
    await api.setVocabMastery("v1", "p1", "mastered");
    expect(calls[0].init.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      profile_id: "p1",
      mastery: "mastered",
    });
  });

  it("paginates grading history with snake_case query params", async () => {
    const calls = installFetch(200, { items: [], total: 0, page: 2, page_size: 50 });
    await api.listGradingHistory("p1", { page: 2, pageSize: 50, kind: "essay" });
    const url = new URL(calls[0].url);
    expect(url.pathname).toBe("/v1/campus/grading/history");
    expect(url.searchParams.get("profile_id")).toBe("p1");
    expect(url.searchParams.get("kind")).toBe("essay");
    expect(url.searchParams.get("page")).toBe("2");
    expect(url.searchParams.get("page_size")).toBe("50");
  });

  it("advances mock exam stages only through legal transitions", async () => {
    const calls = installFetch(200, { id: "m1", current_stage: "listening" });
    await api.advanceMockStage("m1", "listening");
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/mock-exams/m1/stage");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ to: "listening" });
  });

  it("decodes the mock exam's JSON-string locked_stages into the array the console reads", async () => {
    // The backend column is scalar (02 §4.16), so `locked_stages` arrives as '["writing"]'.
    // Reading it as an array is what makes the sheet lock correct rather than substring luck.
    installFetch(200, {
      id: "m1",
      current_stage: "listening",
      locked_stages: '["writing"]',
      remaining_seconds: 900,
      stage_expired: false,
      server_now: "2026-09-16T00:01:00Z",
    });
    const view = await api.getMockExam("m1");
    expect(view.locked_stages).toEqual(["writing"]);

    installFetch(200, { id: "m1", current_stage: "writing", locked_stages: "[]" });
    expect((await api.createMockExam("p1", "paper")).locked_stages).toEqual([]);

    installFetch(200, { id: "m1", current_stage: "writing", locked_stages: [] });
    expect((await api.advanceMockStage("m1", "listening")).locked_stages).toEqual([]);
  });

  it("patches the assessment draft with the profile guard field the backend requires", async () => {
    const calls = installFetch(200, { id: "a1", status: "draft" });
    await api.patchAssessment("a1", "p1", { q1: "A", q2: "" });
    expect(calls[0].init.method).toBe("PATCH");
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/assessments/a1");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      profile_id: "p1",
      answers: { q1: "A", q2: "" },
    });
  });

  it("reports the paused seconds on the pause call (backend MockPause body)", async () => {
    const calls = installFetch(200, { id: "m1" });
    await api.pauseMockExam("m1", 90);
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].url).toBe("http://127.0.0.1:8765/v1/campus/mock-exams/m1/pause");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ seconds: 90 });
  });
});
