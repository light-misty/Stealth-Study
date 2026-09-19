import { describe, expect, it } from "vitest";
import { CAMPUS_ENDPOINTS } from "../api";

const DOC_ROWS: Record<string, { methods: string[]; path: string }> = {
  A1: { methods: ["GET"], path: "/v1/campus/profiles" },
  A2: { methods: ["POST"], path: "/v1/campus/profiles" },
  A3: { methods: ["GET"], path: "/v1/campus/profiles/{pid}" },
  A4: { methods: ["PATCH"], path: "/v1/campus/profiles/{pid}" },
  A5: { methods: ["DELETE"], path: "/v1/campus/profiles/{pid}" },
  A11: { methods: ["GET"], path: "/v1/campus/profiles/{pid}/impact" },
  A6: { methods: ["GET"], path: "/v1/campus/app-state" },
  A7: { methods: ["PATCH"], path: "/v1/campus/app-state" },
  A8: { methods: ["GET"], path: "/v1/campus/capabilities" },
  A9: { methods: ["GET"], path: "/v1/campus/privacy" },
  A10: { methods: ["DELETE"], path: "/v1/campus/privacy/data" },
  B1: { methods: ["POST"], path: "/v1/campus/library/import" },
  B2: { methods: ["GET"], path: "/v1/campus/library" },
  B3: { methods: ["GET"], path: "/v1/campus/library/{doc_id}" },
  B4: { methods: ["DELETE"], path: "/v1/campus/library/{doc_id}" },
  B5: { methods: ["POST"], path: "/v1/campus/library/{doc_id}/retry" },
  B6: { methods: ["POST"], path: "/v1/campus/qa" },
  B7: { methods: ["POST"], path: "/v1/campus/qa/generate-questions" },
  C1: { methods: ["POST"], path: "/v1/campus/grading" },
  C2: { methods: ["GET"], path: "/v1/campus/grading/{attempt_id}" },
  C3: { methods: ["GET"], path: "/v1/campus/grading/history" },
  C4: { methods: ["GET"], path: "/v1/campus/grading/common-errors" },
  D1: { methods: ["GET"], path: "/v1/campus/mistakes" },
  D2: { methods: ["PATCH"], path: "/v1/campus/mistakes/{id}" },
  D3: { methods: ["GET"], path: "/v1/campus/mistakes/stats" },
  D4: { methods: ["POST"], path: "/v1/campus/review/items" },
  D5: { methods: ["GET"], path: "/v1/campus/review/due" },
  D6: { methods: ["POST"], path: "/v1/campus/review/{rq_id}/result" },
  D7: { methods: ["POST"], path: "/v1/campus/review/attributions" },
  E1: { methods: ["POST"], path: "/v1/campus/questions/import" },
  E2: { methods: ["GET"], path: "/v1/campus/questions" },
  E3: { methods: ["POST"], path: "/v1/campus/questions" },
  E4: { methods: ["PATCH", "DELETE"], path: "/v1/campus/questions/{qid}" },
  E5: { methods: ["POST"], path: "/v1/campus/attempts" },
  F1: { methods: ["POST"], path: "/v1/campus/assessments" },
  F2: { methods: ["GET"], path: "/v1/campus/assessments/{id}" },
  F3: { methods: ["PATCH"], path: "/v1/campus/assessments/{id}" },
  F4: { methods: ["POST"], path: "/v1/campus/assessments/{id}/finish" },
  F5: { methods: ["POST"], path: "/v1/campus/plans/generate" },
  F6: { methods: ["GET"], path: "/v1/campus/vocab/today" },
  F7: { methods: ["PATCH"], path: "/v1/campus/vocab/{id}" },
  F8: { methods: ["POST"], path: "/v1/campus/vocab/import" },
  F9: { methods: ["POST"], path: "/v1/campus/vocab/mnemonic" },
  F10: { methods: ["POST"], path: "/v1/campus/mock-exams" },
  F11: { methods: ["GET"], path: "/v1/campus/mock-exams/{id}" },
  F12: { methods: ["POST"], path: "/v1/campus/mock-exams/{id}/stage" },
  F13: { methods: ["POST"], path: "/v1/campus/mock-exams/{id}/pause" },
  F14: { methods: ["POST"], path: "/v1/campus/mock-exams/{id}/submit" },
  G1: { methods: ["GET"], path: "/v1/campus/tasks" },
  G2: { methods: ["PATCH"], path: "/v1/campus/tasks/{id}" },
  G3: { methods: ["POST"], path: "/v1/campus/plans/{plan_id}/reschedule" },
  G4: { methods: ["GET"], path: "/v1/campus/progress" },
  G5: { methods: ["POST"], path: "/v1/campus/weekly-reports/generate" },
  G6: { methods: ["GET"], path: "/v1/campus/weekly-reports" },
  G7: { methods: ["GET"], path: "/v1/campus/school-profile" },
  G8: { methods: ["PATCH"], path: "/v1/campus/school-profile" },
  G9: { methods: ["POST"], path: "/v1/campus/school-profile/extract" },
  H1: { methods: ["GET"], path: "/v1/campus/knowledge-tree" },
  H2: { methods: ["POST"], path: "/v1/campus/knowledge-points" },
  H3: { methods: ["PATCH", "DELETE"], path: "/v1/campus/knowledge-points/{id}" },
  H4: { methods: ["POST"], path: "/v1/campus/knowledge-tree/generate" },
  H5: { methods: ["PATCH"], path: "/v1/campus/mastery" },
  H6: { methods: ["GET"], path: "/v1/campus/mastery/coverage" },
  H7: { methods: ["POST"], path: "/v1/campus/deadlines" },
  H8: { methods: ["GET"], path: "/v1/campus/deadlines" },
  H9: { methods: ["POST"], path: "/v1/campus/deadlines/{id}/reminders" },
  H10: { methods: ["GET"], path: "/v1/campus/reminders" },
  I1: { methods: ["GET"], path: "/v1/campus/personas" },
  I2: { methods: ["GET"], path: "/v1/campus/automation-templates" },
  I3: { methods: ["POST"], path: "/v1/campus/automation-templates/{tpl_id}/install" },
  I4: { methods: ["POST"], path: "/v1/campus/exports" },
  I5: { methods: ["GET"], path: "/v1/campus/exports/{filename}" },
  I6: { methods: ["POST"], path: "/v1/campus/exports/wipe" },
};

describe("campus endpoint contract", () => {
  it("covers the 03 doc endpoint table 73/73 with no extra rows", () => {
    const manifestIds = [...new Set(CAMPUS_ENDPOINTS.map((row) => row.id))].sort();
    const docIds = Object.keys(DOC_ROWS).sort();
    expect(manifestIds).toEqual(docIds);
    expect(manifestIds).toHaveLength(73);
  });

  it("matches the documented method(s) and path for every endpoint row", () => {
    for (const [id, row] of Object.entries(DOC_ROWS)) {
      const ops = CAMPUS_ENDPOINTS.filter((op) => op.id === id);
      expect(ops.map((op) => op.method).sort(), `${id} methods`).toEqual([...row.methods].sort());
      for (const op of ops) {
        expect(op.path, `${id} path`).toBe(row.path);
      }
    }
  });

  it("carries an implementing function for every operation (I5 via URL builder)", () => {
    for (const op of CAMPUS_ENDPOINTS) {
      expect(typeof op.fn, `${op.id} ${op.method} fn`).toBe("function");
    }
  });

  it("has no duplicate method+path pairs and unique function names", () => {
    const pairs = CAMPUS_ENDPOINTS.map((op) => `${op.method} ${op.path}`);
    expect(new Set(pairs).size).toBe(pairs.length);
    const names = CAMPUS_ENDPOINTS.map((op) => (op.fn as { name: string }).name);
    expect(new Set(names).size).toBe(names.length);
    expect(names).toHaveLength(75);
  });
});
