import type {
  AppStatePatch,
  Assessment,
  AssessmentFinishResult,
  Attempt,
  AttemptSubmitInput,
  AttributionSuggestion,
  AutomationTemplateSummary,
  CapabilitiesReport,
  CampusAppState,
  CampusPersonaSummary,
  CampusTrack,
  CertDeadline,
  ClearPrivacyResult,
  DeadlineCreateInput,
  DeadlineView,
  ExamProfile,
  ExportResult,
  GenerateQuestionsInput,
  GradingHistoryFilters,
  GradingKind,
  GradingSubmitInput,
  KnowledgePoint,
  KnowledgePointCreateInput,
  KnowledgePointNode,
  KnowledgePointPatch,
  KnowledgeTreeGenerateInput,
  LibraryQAAnswer,
  ListPage,
  Mastery,
  MasteryCoverage,
  MasteryLevel,
  MasteryPatch,
  MistakeBookEntry,
  MistakeFilters,
  MistakePatch,
  MistakeStats,
  MockExam,
  MockExamView,
  MockStage,
  MockSubmitResult,
  Paged,
  PlanGenerationResult,
  PlanTask,
  PrivacyReport,
  ProfileCreateInput,
  ProfilePatch,
  ProfileStatus,
  ProgressReport,
  QuestionBankItem,
  QuestionCreateInput,
  QuestionFilters,
  QuestionPatch,
  RescheduleResult,
  ReviewDueItem,
  ReviewItem,
  ReviewItemType,
  SchoolProfile,
  SchoolProfileExtractInput,
  SchoolProfilePatch,
  SourceDoc,
  GradeResult,
  TaskFilters,
  TaskPatch,
  VocabItem,
  VocabToday,
  WeeklyReport,
} from "./types";

declare const __COWORKER_DEV_TOKEN__: string;

const httpBase = (): string =>
  (globalThis as any).__COWORKER_HTTP__ ||
  (import.meta as any).env?.VITE_COWORKER_HTTP ||
  "http://127.0.0.1:8765";
const apiToken = (): string =>
  (globalThis as any).__COWORKER_API_TOKEN__ ||
  (import.meta as any).env?.VITE_COWORKER_API_TOKEN ||
  (typeof __COWORKER_DEV_TOKEN__ === "string" ? __COWORKER_DEV_TOKEN__ : "");

export class CampusApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public retryable: boolean,
    public status: number,
  ) {
    super(message);
    this.name = "CampusApiError";
  }
}

const request = async (path: string, init: RequestInit = {}): Promise<any> => {
  const headers = new Headers(init.headers);
  const token = apiToken();
  if (token) headers.set("X-SS-Token", token);
  if (typeof init.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await globalThis.fetch(httpBase() + path, { ...init, headers });
  if (!res.ok) throw await toCampusError(res);
  return res.status === 204 ? null : res.json();
};

const toCampusError = async (res: Response): Promise<CampusApiError> => {
  let payload: unknown = null;
  try {
    payload = await res.json();
  } catch {
    payload = null;
  }
  const detail = (payload as { detail?: unknown } | null)?.detail;
  if (detail && typeof detail === "object") {
    const d = detail as { code?: unknown; message?: unknown; retryable?: unknown };
    return new CampusApiError(
      typeof d.code === "string" ? d.code : "UNKNOWN",
      typeof d.message === "string" ? d.message : "",
      d.retryable === true,
      res.status,
    );
  }
  return new CampusApiError(
    "UNKNOWN",
    typeof detail === "string" ? detail : "",
    res.status >= 500 && res.status !== 507,
    res.status,
  );
};

const qs = (params: Record<string, string | number | undefined | null>): string => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

const pageParams = (page?: ListPage): Record<string, string | number | undefined> =>
  page ? { page: page.page, page_size: page.pageSize } : {};

const idempotencyHeaders = (key?: string): Record<string, string> =>
  key ? { "Idempotency-Key": key } : {};

export async function listProfiles(
  track?: CampusTrack,
  status?: ProfileStatus,
): Promise<{ items: ExamProfile[] }> {
  return request(`/v1/campus/profiles${qs({ track, status })}`);
}

export async function createProfile(
  input: ProfileCreateInput,
  idempotencyKey?: string,
): Promise<ExamProfile> {
  return request("/v1/campus/profiles", {
    method: "POST",
    body: JSON.stringify(input),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function getProfile(profileId: string): Promise<ExamProfile> {
  return request(`/v1/campus/profiles/${profileId}`);
}

export async function patchProfile(profileId: string, patch: ProfilePatch): Promise<ExamProfile> {
  return request(`/v1/campus/profiles/${profileId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteProfile(
  profileId: string,
): Promise<{ deleted: boolean; cascade: Record<string, number> }> {
  return request(`/v1/campus/profiles/${profileId}`, { method: "DELETE" });
}

export async function getAppState(): Promise<CampusAppState> {
  return request("/v1/campus/app-state");
}

export async function patchAppState(patch: AppStatePatch): Promise<CampusAppState> {
  return request("/v1/campus/app-state", { method: "PATCH", body: JSON.stringify(patch) });
}

export async function getCapabilities(): Promise<CapabilitiesReport> {
  return request("/v1/campus/capabilities");
}

export async function getPrivacy(): Promise<PrivacyReport> {
  return request("/v1/campus/privacy");
}

export async function clearPrivacyData(): Promise<ClearPrivacyResult> {
  return request("/v1/campus/privacy/data", { method: "DELETE" });
}

export async function importLibraryDoc(
  profileId: string,
  file: File,
  idempotencyKey?: string,
): Promise<SourceDoc> {
  const form = new FormData();
  form.set("profile_id", profileId);
  form.set("file", file);
  return request("/v1/campus/library/import", {
    method: "POST",
    body: form,
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function listLibraryDocs(
  profileId: string,
  parseStatus?: string,
): Promise<{ items: SourceDoc[] }> {
  return request(`/v1/campus/library${qs({ profile_id: profileId, parse_status: parseStatus })}`);
}

export async function getLibraryDoc(docId: string): Promise<SourceDoc> {
  return request(`/v1/campus/library/${docId}`);
}

export async function deleteLibraryDoc(docId: string): Promise<{ deleted: boolean } | null> {
  return request(`/v1/campus/library/${docId}`, { method: "DELETE" });
}

export async function retryLibraryDoc(
  docId: string,
  idempotencyKey?: string,
): Promise<SourceDoc> {
  return request(`/v1/campus/library/${docId}/retry`, {
    method: "POST",
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function askLibrary(
  profileId: string,
  question: string,
  docId?: string,
): Promise<LibraryQAAnswer> {
  return request("/v1/campus/qa", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, question, doc_id: docId }),
  });
}

export async function generateQuestionsFromDoc(
  input: GenerateQuestionsInput,
): Promise<{ items: QuestionBankItem[] }> {
  return request("/v1/campus/qa/generate-questions", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      doc_id: input.docId,
      point_id: input.pointId,
      count: input.count,
    }),
  });
}

export async function submitGrading(input: GradingSubmitInput): Promise<GradeResult> {
  return request("/v1/campus/grading", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      question_id: input.questionId,
      kind: input.kind,
      answer: input.answer,
      rubric_id: input.rubricId,
      custom_rubric: input.customRubric,
    }),
  });
}

export async function getAttempt(attemptId: string): Promise<Attempt> {
  return request(`/v1/campus/grading/${attemptId}`);
}

export async function listGradingHistory(
  profileId: string,
  filters: GradingHistoryFilters = {},
): Promise<Paged<Attempt>> {
  return request(
    `/v1/campus/grading/history${qs({
      profile_id: profileId,
      subject: filters.subject,
      kind: filters.kind,
      ...pageParams(filters),
    })}`,
  );
}

export async function getCommonErrors(
  profileId: string,
  kind?: GradingKind,
): Promise<{ top3: { type: string; count: number; samples: string[] }[] }> {
  return request(`/v1/campus/grading/common-errors${qs({ profile_id: profileId, kind })}`);
}

export async function listMistakes(
  profileId: string,
  filters: MistakeFilters = {},
): Promise<Paged<MistakeBookEntry>> {
  return request(
    `/v1/campus/mistakes${qs({
      profile_id: profileId,
      attribution: filters.attribution,
      resolved: filters.resolved,
      point_id: filters.point_id,
      track_type: filters.track_type,
      ...pageParams(filters),
    })}`,
  );
}

export async function patchMistake(id: string, patch: MistakePatch): Promise<MistakeBookEntry> {
  return request(`/v1/campus/mistakes/${id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function getMistakeStats(profileId: string): Promise<MistakeStats> {
  return request(`/v1/campus/mistakes/stats${qs({ profile_id: profileId })}`);
}

export async function addReviewItem(
  profileId: string,
  itemType: ReviewItemType,
  itemId: string,
): Promise<ReviewItem> {
  return request("/v1/campus/review/items", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, item_type: itemType, item_id: itemId }),
  });
}

export async function listDueReviews(
  profileId: string,
  asOf?: string,
): Promise<{ items: ReviewDueItem[] }> {
  return request(`/v1/campus/review/due${qs({ profile_id: profileId, as_of: asOf })}`);
}

export async function submitReviewResult(
  reviewId: string,
  correct: boolean,
): Promise<ReviewItem> {
  return request(`/v1/campus/review/${reviewId}/result`, {
    method: "POST",
    body: JSON.stringify({ correct }),
  });
}

export async function suggestAttributions(
  profileId: string,
  attemptIds: string[],
): Promise<{ items: AttributionSuggestion[] }> {
  return request("/v1/campus/review/attributions", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, attempt_ids: attemptIds }),
  });
}

export async function importQuestions(
  profileId: string,
  format: "md" | "csv",
  content: string,
  idempotencyKey?: string,
): Promise<{ imported: number; skipped: number; items: QuestionBankItem[] }> {
  return request("/v1/campus/questions/import", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, format, content }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function listQuestions(
  profileId: string,
  filters: QuestionFilters = {},
): Promise<Paged<QuestionBankItem>> {
  return request(
    `/v1/campus/questions${qs({
      profile_id: profileId,
      point_id: filters.point_id,
      qtype: filters.qtype,
      subject: filters.subject,
      ...pageParams(filters),
    })}`,
  );
}

export async function createQuestion(
  input: QuestionCreateInput,
  idempotencyKey?: string,
): Promise<QuestionBankItem> {
  return request("/v1/campus/questions", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      subject: input.subject,
      stem: input.stem,
      qtype: input.qtype,
      point_id: input.pointId,
      options: input.options,
      answer: input.answer,
      answer_meta: input.answerMeta,
      max_score: input.maxScore,
      difficulty: input.difficulty,
      source: input.source,
      doc_id: input.docId,
    }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function patchQuestion(qid: string, patch: QuestionPatch): Promise<QuestionBankItem> {
  return request(`/v1/campus/questions/${qid}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export async function deleteQuestion(qid: string): Promise<{ deleted: boolean }> {
  return request(`/v1/campus/questions/${qid}`, { method: "DELETE" });
}

export async function submitAttempt(input: AttemptSubmitInput): Promise<Attempt> {
  return request("/v1/campus/attempts", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      question_id: input.questionId,
      session_type: input.sessionType,
      mock_exam_id: input.mockExamId,
      answer: input.answer,
    }),
  });
}

export async function createAssessment(
  profileId: string,
  idempotencyKey?: string,
): Promise<Assessment> {
  return request("/v1/campus/assessments", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function getAssessment(assessmentId: string): Promise<Assessment> {
  return request(`/v1/campus/assessments/${assessmentId}`);
}

export async function patchAssessment(
  assessmentId: string,
  profileId: string,
  answers: Record<string, string>,
): Promise<Assessment> {
  return request(`/v1/campus/assessments/${assessmentId}`, {
    method: "PATCH",
    body: JSON.stringify({ profile_id: profileId, answers }),
  });
}

export async function finishAssessment(assessmentId: string): Promise<AssessmentFinishResult> {
  return request(`/v1/campus/assessments/${assessmentId}/finish`, { method: "POST" });
}

export async function generatePlan(profileId: string): Promise<PlanGenerationResult> {
  return request("/v1/campus/plans/generate", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function listVocabToday(profileId: string): Promise<VocabToday> {
  return request(`/v1/campus/vocab/today${qs({ profile_id: profileId })}`);
}

export async function setVocabMastery(
  vocabId: string,
  profileId: string,
  mastery: MasteryLevel,
): Promise<VocabItem> {
  return request(`/v1/campus/vocab/${vocabId}`, {
    method: "PATCH",
    body: JSON.stringify({ profile_id: profileId, mastery }),
  });
}

export async function importVocab(
  profileId: string,
  format: "csv" | "md",
  content: string,
  idempotencyKey?: string,
): Promise<{ imported: number; skipped: number }> {
  return request("/v1/campus/vocab/import", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, format, content }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function makeMnemonic(vocabId: string): Promise<{ mnemonic: string }> {
  return request("/v1/campus/vocab/mnemonic", {
    method: "POST",
    body: JSON.stringify({ vocab_id: vocabId }),
  });
}

export async function createMockExam(
  profileId: string,
  paperTitle: string,
  idempotencyKey?: string,
): Promise<MockExam> {
  return request("/v1/campus/mock-exams", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, paper_title: paperTitle }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function getMockExam(mockExamId: string): Promise<MockExamView> {
  return request(`/v1/campus/mock-exams/${mockExamId}`);
}

export async function advanceMockStage(
  mockExamId: string,
  to: Exclude<MockStage, "writing" | "graded">,
): Promise<MockExam> {
  return request(`/v1/campus/mock-exams/${mockExamId}/stage`, {
    method: "POST",
    body: JSON.stringify({ to }),
  });
}

export async function pauseMockExam(mockExamId: string, seconds: number): Promise<MockExamView> {
  return request(`/v1/campus/mock-exams/${mockExamId}/pause`, {
    method: "POST",
    body: JSON.stringify({ seconds }),
  });
}

export async function submitMockExam(mockExamId: string): Promise<MockSubmitResult> {
  return request(`/v1/campus/mock-exams/${mockExamId}/submit`, { method: "POST" });
}

export async function listTasks(
  profileId: string,
  filters: TaskFilters = {},
): Promise<{ items: PlanTask[] }> {
  return request(
    `/v1/campus/tasks${qs({
      profile_id: profileId,
      date: filters.date,
      status: filters.status,
      track: filters.track,
    })}`,
  );
}

export async function patchTask(taskId: string, patch: TaskPatch): Promise<PlanTask> {
  return request(`/v1/campus/tasks/${taskId}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export async function reschedulePlan(
  planId: string,
  newExamDate?: string,
): Promise<RescheduleResult> {
  return request(`/v1/campus/plans/${planId}/reschedule`, {
    method: "POST",
    body: JSON.stringify({ new_exam_date: newExamDate }),
  });
}

export async function getProgress(profileId: string): Promise<ProgressReport> {
  return request(`/v1/campus/progress${qs({ profile_id: profileId })}`);
}

export async function generateWeeklyReport(profileId: string): Promise<WeeklyReport> {
  return request("/v1/campus/weekly-reports/generate", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function listWeeklyReports(profileId: string): Promise<{ items: WeeklyReport[] }> {
  return request(`/v1/campus/weekly-reports${qs({ profile_id: profileId })}`);
}

export async function getSchoolProfile(profileId: string): Promise<SchoolProfile> {
  return request(`/v1/campus/school-profile${qs({ profile_id: profileId })}`);
}

export async function patchSchoolProfile(
  profileId: string,
  patch: SchoolProfilePatch,
): Promise<SchoolProfile> {
  return request("/v1/campus/school-profile", {
    method: "PATCH",
    body: JSON.stringify({ profile_id: profileId, ...patch }),
  });
}

export async function extractSchoolProfile(input: SchoolProfileExtractInput): Promise<{
  prefill: Partial<SchoolProfilePatch>;
  confidence: number;
}> {
  return request("/v1/campus/school-profile/extract", {
    method: "POST",
    body: JSON.stringify({ profile_id: input.profileId, text: input.text }),
  });
}

export async function getKnowledgeTree(profileId: string): Promise<{ roots: KnowledgePointNode[] }> {
  return request(`/v1/campus/knowledge-tree${qs({ profile_id: profileId })}`);
}

export async function createKnowledgePoint(
  input: KnowledgePointCreateInput,
): Promise<KnowledgePoint> {
  return request("/v1/campus/knowledge-points", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      parent_id: input.parent_id,
      title: input.title,
      desc: input.desc,
      order_index: input.order_index,
    }),
  });
}

export async function patchKnowledgePoint(
  pointId: string,
  patch: KnowledgePointPatch,
): Promise<KnowledgePoint> {
  return request(`/v1/campus/knowledge-points/${pointId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function deleteKnowledgePoint(
  pointId: string,
): Promise<{ deleted: boolean; orphaned_children: number }> {
  return request(`/v1/campus/knowledge-points/${pointId}`, { method: "DELETE" });
}

export async function generateKnowledgeTree(
  input: KnowledgeTreeGenerateInput,
): Promise<{ created: number; roots: KnowledgePointNode[] }> {
  return request("/v1/campus/knowledge-tree/generate", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      text: input.text,
      doc_id: input.docId,
    }),
  });
}

export async function setMastery(profileId: string, patch: MasteryPatch): Promise<Mastery> {
  return request("/v1/campus/mastery", {
    method: "PATCH",
    body: JSON.stringify({
      profile_id: profileId,
      point_id: patch.pointId,
      dimension: patch.dimension,
      level: patch.level,
    }),
  });
}

export async function getMasteryCoverage(profileId: string): Promise<MasteryCoverage> {
  return request(`/v1/campus/mastery/coverage${qs({ profile_id: profileId })}`);
}

export async function createDeadline(
  input: DeadlineCreateInput,
  idempotencyKey?: string,
): Promise<CertDeadline> {
  return request("/v1/campus/deadlines", {
    method: "POST",
    body: JSON.stringify({
      profile_id: input.profileId,
      node_type: input.nodeType,
      date: input.date,
      is_reference: input.isReference,
    }),
    headers: idempotencyHeaders(idempotencyKey),
  });
}

export async function listDeadlines(
  profileId: string,
): Promise<{ items: (CertDeadline & { days_left: number })[] }> {
  return request(`/v1/campus/deadlines${qs({ profile_id: profileId })}`);
}

export async function createDeadlineReminders(
  deadlineId: string,
): Promise<{ automation_ids: string[] }> {
  return request(`/v1/campus/deadlines/${deadlineId}/reminders`, { method: "POST" });
}

export async function getReminders(profileId: string): Promise<{
  banner: DeadlineView[];
  expired: DeadlineView[];
}> {
  return request(`/v1/campus/reminders${qs({ profile_id: profileId })}`);
}

export async function listCampusPersonas(): Promise<{ items: CampusPersonaSummary[] }> {
  return request("/v1/campus/personas");
}

export async function listAutomationTemplates(): Promise<{
  items: AutomationTemplateSummary[];
}> {
  return request("/v1/campus/automation-templates");
}

export async function installAutomationTemplate(
  templateId: string,
  profileId: string,
): Promise<{ task_ids: string[] }> {
  return request(`/v1/campus/automation-templates/${templateId}/install`, {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
}

export async function exportData(
  profileId: string,
  format: "md" | "json" | "csv",
): Promise<ExportResult> {
  return request("/v1/campus/exports", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId, format }),
  });
}

export function exportDownloadUrl(filename: string): string {
  return `${httpBase()}/v1/campus/exports/${encodeURIComponent(filename)}`;
}

export async function wipeCampusData(): Promise<{ wiped: boolean }> {
  return request("/v1/campus/exports/wipe", { method: "POST" });
}

export interface CampusEndpointRef {
  id: string;
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  fn: (...args: never[]) => unknown;
}

export const CAMPUS_ENDPOINTS: CampusEndpointRef[] = [
  { id: "A1", method: "GET", path: "/v1/campus/profiles", fn: listProfiles },
  { id: "A2", method: "POST", path: "/v1/campus/profiles", fn: createProfile },
  { id: "A3", method: "GET", path: "/v1/campus/profiles/{pid}", fn: getProfile },
  { id: "A4", method: "PATCH", path: "/v1/campus/profiles/{pid}", fn: patchProfile },
  { id: "A5", method: "DELETE", path: "/v1/campus/profiles/{pid}", fn: deleteProfile },
  { id: "A6", method: "GET", path: "/v1/campus/app-state", fn: getAppState },
  { id: "A7", method: "PATCH", path: "/v1/campus/app-state", fn: patchAppState },
  { id: "A8", method: "GET", path: "/v1/campus/capabilities", fn: getCapabilities },
  { id: "A9", method: "GET", path: "/v1/campus/privacy", fn: getPrivacy },
  { id: "A10", method: "DELETE", path: "/v1/campus/privacy/data", fn: clearPrivacyData },
  { id: "B1", method: "POST", path: "/v1/campus/library/import", fn: importLibraryDoc },
  { id: "B2", method: "GET", path: "/v1/campus/library", fn: listLibraryDocs },
  { id: "B3", method: "GET", path: "/v1/campus/library/{doc_id}", fn: getLibraryDoc },
  { id: "B4", method: "DELETE", path: "/v1/campus/library/{doc_id}", fn: deleteLibraryDoc },
  { id: "B5", method: "POST", path: "/v1/campus/library/{doc_id}/retry", fn: retryLibraryDoc },
  { id: "B6", method: "POST", path: "/v1/campus/qa", fn: askLibrary },
  {
    id: "B7",
    method: "POST",
    path: "/v1/campus/qa/generate-questions",
    fn: generateQuestionsFromDoc,
  },
  { id: "C1", method: "POST", path: "/v1/campus/grading", fn: submitGrading },
  { id: "C2", method: "GET", path: "/v1/campus/grading/{attempt_id}", fn: getAttempt },
  { id: "C3", method: "GET", path: "/v1/campus/grading/history", fn: listGradingHistory },
  {
    id: "C4",
    method: "GET",
    path: "/v1/campus/grading/common-errors",
    fn: getCommonErrors,
  },
  { id: "D1", method: "GET", path: "/v1/campus/mistakes", fn: listMistakes },
  { id: "D2", method: "PATCH", path: "/v1/campus/mistakes/{id}", fn: patchMistake },
  { id: "D3", method: "GET", path: "/v1/campus/mistakes/stats", fn: getMistakeStats },
  { id: "D4", method: "POST", path: "/v1/campus/review/items", fn: addReviewItem },
  { id: "D5", method: "GET", path: "/v1/campus/review/due", fn: listDueReviews },
  { id: "D6", method: "POST", path: "/v1/campus/review/{rq_id}/result", fn: submitReviewResult },
  { id: "D7", method: "POST", path: "/v1/campus/review/attributions", fn: suggestAttributions },
  { id: "E1", method: "POST", path: "/v1/campus/questions/import", fn: importQuestions },
  { id: "E2", method: "GET", path: "/v1/campus/questions", fn: listQuestions },
  { id: "E3", method: "POST", path: "/v1/campus/questions", fn: createQuestion },
  { id: "E4", method: "PATCH", path: "/v1/campus/questions/{qid}", fn: patchQuestion },
  { id: "E4", method: "DELETE", path: "/v1/campus/questions/{qid}", fn: deleteQuestion },
  { id: "E5", method: "POST", path: "/v1/campus/attempts", fn: submitAttempt },
  { id: "F1", method: "POST", path: "/v1/campus/assessments", fn: createAssessment },
  { id: "F2", method: "GET", path: "/v1/campus/assessments/{id}", fn: getAssessment },
  { id: "F3", method: "PATCH", path: "/v1/campus/assessments/{id}", fn: patchAssessment },
  {
    id: "F4",
    method: "POST",
    path: "/v1/campus/assessments/{id}/finish",
    fn: finishAssessment,
  },
  { id: "F5", method: "POST", path: "/v1/campus/plans/generate", fn: generatePlan },
  { id: "F6", method: "GET", path: "/v1/campus/vocab/today", fn: listVocabToday },
  { id: "F7", method: "PATCH", path: "/v1/campus/vocab/{id}", fn: setVocabMastery },
  { id: "F8", method: "POST", path: "/v1/campus/vocab/import", fn: importVocab },
  { id: "F9", method: "POST", path: "/v1/campus/vocab/mnemonic", fn: makeMnemonic },
  { id: "F10", method: "POST", path: "/v1/campus/mock-exams", fn: createMockExam },
  { id: "F11", method: "GET", path: "/v1/campus/mock-exams/{id}", fn: getMockExam },
  {
    id: "F12",
    method: "POST",
    path: "/v1/campus/mock-exams/{id}/stage",
    fn: advanceMockStage,
  },
  { id: "F13", method: "POST", path: "/v1/campus/mock-exams/{id}/pause", fn: pauseMockExam },
  { id: "F14", method: "POST", path: "/v1/campus/mock-exams/{id}/submit", fn: submitMockExam },
  { id: "G1", method: "GET", path: "/v1/campus/tasks", fn: listTasks },
  { id: "G2", method: "PATCH", path: "/v1/campus/tasks/{id}", fn: patchTask },
  {
    id: "G3",
    method: "POST",
    path: "/v1/campus/plans/{plan_id}/reschedule",
    fn: reschedulePlan,
  },
  { id: "G4", method: "GET", path: "/v1/campus/progress", fn: getProgress },
  {
    id: "G5",
    method: "POST",
    path: "/v1/campus/weekly-reports/generate",
    fn: generateWeeklyReport,
  },
  { id: "G6", method: "GET", path: "/v1/campus/weekly-reports", fn: listWeeklyReports },
  { id: "G7", method: "GET", path: "/v1/campus/school-profile", fn: getSchoolProfile },
  { id: "G8", method: "PATCH", path: "/v1/campus/school-profile", fn: patchSchoolProfile },
  {
    id: "G9",
    method: "POST",
    path: "/v1/campus/school-profile/extract",
    fn: extractSchoolProfile,
  },
  { id: "H1", method: "GET", path: "/v1/campus/knowledge-tree", fn: getKnowledgeTree },
  { id: "H2", method: "POST", path: "/v1/campus/knowledge-points", fn: createKnowledgePoint },
  {
    id: "H3",
    method: "PATCH",
    path: "/v1/campus/knowledge-points/{id}",
    fn: patchKnowledgePoint,
  },
  {
    id: "H3",
    method: "DELETE",
    path: "/v1/campus/knowledge-points/{id}",
    fn: deleteKnowledgePoint,
  },
  {
    id: "H4",
    method: "POST",
    path: "/v1/campus/knowledge-tree/generate",
    fn: generateKnowledgeTree,
  },
  { id: "H5", method: "PATCH", path: "/v1/campus/mastery", fn: setMastery },
  { id: "H6", method: "GET", path: "/v1/campus/mastery/coverage", fn: getMasteryCoverage },
  { id: "H7", method: "POST", path: "/v1/campus/deadlines", fn: createDeadline },
  { id: "H8", method: "GET", path: "/v1/campus/deadlines", fn: listDeadlines },
  {
    id: "H9",
    method: "POST",
    path: "/v1/campus/deadlines/{id}/reminders",
    fn: createDeadlineReminders,
  },
  { id: "H10", method: "GET", path: "/v1/campus/reminders", fn: getReminders },
  { id: "I1", method: "GET", path: "/v1/campus/personas", fn: listCampusPersonas },
  {
    id: "I2",
    method: "GET",
    path: "/v1/campus/automation-templates",
    fn: listAutomationTemplates,
  },
  {
    id: "I3",
    method: "POST",
    path: "/v1/campus/automation-templates/{tpl_id}/install",
    fn: installAutomationTemplate,
  },
  { id: "I4", method: "POST", path: "/v1/campus/exports", fn: exportData },
  { id: "I5", method: "GET", path: "/v1/campus/exports/{filename}", fn: exportDownloadUrl },
  { id: "I6", method: "POST", path: "/v1/campus/exports/wipe", fn: wipeCampusData },
];
