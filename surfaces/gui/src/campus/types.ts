export const CAMPUS_TRACKS = ["cet", "kaoyan", "cert"] as const;
export type CampusTrack = (typeof CAMPUS_TRACKS)[number];

export const PROFILE_TRACK_TYPES = [...CAMPUS_TRACKS, "other"] as const;
export type ProfileTrackType = (typeof PROFILE_TRACK_TYPES)[number];

export const CERT_TYPES = ["teaching", "ncre", "law", "cpa", "other"] as const;
export type CertType = (typeof CERT_TYPES)[number];

export const CET_LEVELS = ["cet4", "cet6"] as const;
export type CetLevel = (typeof CET_LEVELS)[number];

export const PROFILE_STATUSES = ["active", "archived", "finished"] as const;
export type ProfileStatus = (typeof PROFILE_STATUSES)[number];

export const DEGREE_TYPES = ["academic", "professional"] as const;
export type DegreeType = (typeof DEGREE_TYPES)[number];

export const DOC_FILE_TYPES = ["pdf", "md", "txt"] as const;
export type DocFileType = (typeof DOC_FILE_TYPES)[number];

export const PARSE_STATUSES = ["pending", "ready", "failed"] as const;
export type ParseStatus = (typeof PARSE_STATUSES)[number];

export const KNOWLEDGE_SOURCES = ["manual", "ai_generated", "imported"] as const;
export type KnowledgeSource = (typeof KNOWLEDGE_SOURCES)[number];

export const MASTERY_LEVELS = ["unknown", "fuzzy", "mastered"] as const;
export type MasteryLevel = (typeof MASTERY_LEVELS)[number];

export const MASTERY_DIMENSIONS = [
  "concept",
  "listening",
  "reading",
  "writing",
  "translation",
] as const;
export type MasteryDimension = (typeof MASTERY_DIMENSIONS)[number];

export const SUBJECTS = [
  "listening",
  "reading",
  "writing",
  "translation",
  "vocab",
  "politics",
  "english",
  "math",
  "major",
] as const;
export type Subject = (typeof SUBJECTS)[number];

export const PLAN_TRACKS = ["overall", "politics", "english", "math", "major"] as const;
export type PlanTrack = (typeof PLAN_TRACKS)[number];

export const PLAN_STAGES = ["foundation", "intensive", "pastpaper", "sprint"] as const;
export type PlanStage = (typeof PLAN_STAGES)[number];

export const PLAN_SOURCES = ["ai_generated", "manual"] as const;
export type PlanSource = (typeof PLAN_SOURCES)[number];

export const TASK_STATUSES = ["todo", "doing", "review", "done", "skipped"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

export const EXAMPLE_SOURCES = ["past_paper", "ai"] as const;
export type ExampleSource = (typeof EXAMPLE_SOURCES)[number];

export const QUESTION_TYPES = [
  "single",
  "multiple",
  "judge",
  "blank",
  "short_answer",
  "essay",
  "material",
  "lesson_plan",
  "practical",
] as const;
export type QuestionType = (typeof QUESTION_TYPES)[number];

export const QUESTION_SOURCES = ["manual", "ai", "imported", "past_paper"] as const;
export type QuestionSource = (typeof QUESTION_SOURCES)[number];

export const SESSION_TYPES = ["practice", "mock", "assessment", "grading"] as const;
export type SessionType = (typeof SESSION_TYPES)[number];

export const ATTRIBUTIONS = [
  "concept_unclear",
  "misread",
  "calculation_or_operation",
  "out_of_scope",
  "time_short",
  "pending",
] as const;
export type Attribution = (typeof ATTRIBUTIONS)[number];

export const REVIEW_ITEM_TYPES = ["mistake", "vocab", "knowledge_point"] as const;
export type ReviewItemType = (typeof REVIEW_ITEM_TYPES)[number];

export const REVIEW_STATUSES = ["pending", "done", "dropped"] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

export const MOCK_STAGES = ["writing", "listening", "reading_translation", "graded"] as const;
export type MockStage = (typeof MOCK_STAGES)[number];

export const MOCK_STATUSES = ["ongoing", "submitted", "graded", "abandoned"] as const;
export type MockStatus = (typeof MOCK_STATUSES)[number];

export const ASSESSMENT_STATUSES = ["draft", "finished"] as const;
export type AssessmentStatus = (typeof ASSESSMENT_STATUSES)[number];

export const DEADLINE_NODE_TYPES = [
  "registration_open",
  "registration_close",
  "payment_close",
  "admission_ticket",
  "exam",
  "score_query",
] as const;
export type DeadlineNodeType = (typeof DEADLINE_NODE_TYPES)[number];

export const REVIEW_INTENSITIES = ["light", "standard", "intense"] as const;
export type ReviewIntensity = (typeof REVIEW_INTENSITIES)[number];

export const GRADING_KINDS = [
  "essay",
  "translation",
  "short_answer",
  "essay_material",
  "lesson_plan",
  "practical",
] as const;
export type GradingKind = (typeof GRADING_KINDS)[number];

export const CAMPUS_TASKS = ["grading", "question", "explain"] as const;
export type CampusTask = (typeof CAMPUS_TASKS)[number];

export type DegradeLevel = 0 | 1 | 2 | 3;

export interface ExamProfile {
  id: string;
  track_type: ProfileTrackType;
  title: string;
  cert_type: CertType | null;
  level: CetLevel | null;
  exam_date: string | null;
  target_score: number | null;
  current_estimate: number | null;
  subjects: string[];
  daily_minutes: number;
  status: ProfileStatus;
  created_at: string;
  updated_at: string;
}

export interface SchoolProfile {
  id: string;
  profile_id: string;
  school: string;
  major: string;
  degree_type: DegreeType | null;
  subjects: string[];
  enroll_count: number | null;
  recommend_ratio: number | null;
  past_scores: { year: number; line: number }[];
  books: string[];
  note: string;
  created_at: string;
  updated_at: string;
}

export interface SourceDoc {
  id: string;
  profile_id: string;
  title: string;
  file_path: string;
  file_type: DocFileType;
  page_count: number;
  parse_status: ParseStatus;
  fail_reason: string | null;
  chunk_count: number;
  char_count: number;
  imported_at: string;
}

export interface KnowledgePoint {
  id: string;
  profile_id: string;
  title: string;
  parent_id: string | null;
  desc: string | null;
  order_index: number;
  source: KnowledgeSource;
  question_count: number;
  mistake_count: number;
  created_at: string;
  updated_at: string;
}

export interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[];
}

export interface Mastery {
  id: string;
  profile_id: string;
  level: MasteryLevel;
  point_id: string | null;
  dimension: MasteryDimension | null;
  score_0_100: number | null;
  evidence: string;
  updated_at: string;
}

export interface StudyPlan {
  id: string;
  profile_id: string;
  track: PlanTrack | null;
  stage: PlanStage | null;
  start_date: string | null;
  end_date: string | null;
  goal_desc: string;
  source: PlanSource;
  created_at: string;
  updated_at: string;
}

export interface PlanTask {
  id: string;
  plan_id: string;
  profile_id: string;
  title: string;
  detail: string;
  subject: string;
  scheduled_date: string;
  est_minutes: number;
  priority: number;
  status: TaskStatus;
  board_card_id: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface VocabItem {
  id: string;
  profile_id: string;
  word: string;
  phonetic: string;
  meaning: string;
  example: string;
  example_source: ExampleSource;
  freq_rank: number | null;
  mastery: MasteryLevel;
  created_at: string;
  updated_at: string;
}

export interface QuestionOption {
  key: string;
  text: string;
}

export interface QuestionBankItem {
  id: string;
  profile_id: string;
  subject: string;
  stem: string;
  qtype: QuestionType;
  point_id: string | null;
  options: QuestionOption[] | null;
  answer: string | null;
  answer_meta: Record<string, unknown> | null;
  max_score: number;
  difficulty: number | null;
  source: QuestionSource;
  doc_id: string | null;
  created_at: string;
}

export interface GradeDimension {
  name: string;
  score: number;
  max: number;
  comment: string;
}

export interface GradingError {
  original: string;
  suggestion: string;
  type: string;
  offset: number | null;
}

export interface GradeResult {
  attempt_id: string;
  degrade_level: DegradeLevel;
  rubric: string;
  dimensions: GradeDimension[];
  errors: GradingError[];
  model_answer_outline: string;
  model_used: string;
  notice: string | null;
}

export interface Attempt {
  id: string;
  profile_id: string;
  track_type: CampusTrack;
  subject: string;
  user_answer: string;
  question_id: string | null;
  session_type: SessionType;
  mock_exam_id: string | null;
  is_correct: number | null;
  score: number | null;
  max_score: number | null;
  grading_json: string | null;
  degrade_level: DegradeLevel | null;
  model_used: string | null;
  created_at: string;
}

export interface MistakeBookEntry {
  id: string;
  profile_id: string;
  attempt_id: string;
  track_type: CampusTrack;
  subject: string;
  question_id: string | null;
  point_id: string | null;
  attribution: Attribution;
  attribution_confidence: number | null;
  wrong_count: number;
  last_wrong_at: string;
  resolved: number;
  note: string;
  created_at: string;
  updated_at: string;
}

export interface ReviewItem {
  id: string;
  profile_id: string;
  item_type: ReviewItemType;
  item_id: string;
  due_at: string;
  interval_days: number;
  streak_right: number;
  ease: number;
  status: ReviewStatus;
  last_reviewed_at: string | null;
  created_at: string;
}

export interface ReviewDueItem extends ReviewItem {
  payload: Record<string, unknown>;
}

export interface MockExam {
  id: string;
  profile_id: string;
  paper_title: string;
  started_at: string;
  current_stage: MockStage;
  stage_deadline: string | null;
  paused_seconds: number;
  locked_stages: MockStage[];
  status: MockStatus;
  estimate_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface AssessmentScores {
  listening: number;
  reading: number;
  writing_translation: number;
  estimate_total: number;
}

export interface Assessment {
  id: string;
  profile_id: string;
  started_at: string;
  status: AssessmentStatus;
  question_ids: string[];
  answers: Record<string, string>;
  scores: AssessmentScores | null;
  finished_at: string | null;
}

export interface WeeklyReport {
  id: string;
  profile_id: string;
  week_start: string;
  week_end: string;
  completion_rate: Record<string, number>;
  top_mistake_points: { point_id: string | null; title: string; count: number }[];
  suggestion: string;
  content_md: string;
  created_at: string;
}

export interface CertDeadline {
  id: string;
  profile_id: string;
  node_type: DeadlineNodeType;
  date: string;
  is_reference: number;
  automation_ids: string[];
  note: string;
  created_at: string;
  updated_at: string;
}

export interface DeadlineView {
  id: string;
  node_type: DeadlineNodeType;
  date: string;
  days_left: number;
  is_reference: boolean;
}

export interface Citation {
  doc_id: string;
  page_no: number;
  snippet: string;
}

export interface LibraryQAAnswer {
  answer: string;
  citations: Citation[];
  used_retrieval: "toc_route" | "keyword";
  chunks_used: number;
}

export interface AttributionSuggestion {
  attempt_id: string;
  suggestion: Attribution;
  confidence_note: string;
}

export interface CampusSettings {
  daily_minutes?: number;
  push_time?: string;
  review_intensity?: ReviewIntensity;
  task_models?: Partial<Record<CampusTask, string>>;
}

export interface CampusAppState {
  active_profile_id: string | null;
  settings: CampusSettings;
}

export interface CapabilityTaskRow {
  task: CampusTask;
  recommended: string;
  minimum: string;
  supported: boolean;
  reason: string | null;
}

export interface CapabilitiesReport {
  current_model: string | null;
  tasks: CapabilityTaskRow[];
}

export interface PrivacyReport {
  data_dir: string;
  library_dir: string;
  db_size_bytes: number;
  model_endpoints: string[];
}

export interface ClearPrivacyResult {
  cleared: boolean;
  freed_bytes: number;
}

export interface CampusPersonaSummary {
  id: string;
  name: string;
  icon: string;
  tagline: string;
  available: boolean;
}

export interface AutomationTemplateSummary {
  id: string;
  title: string;
  cron_desc: string;
  kind: string;
}

export interface ExportResult {
  filename: string;
  path: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MistakeStats {
  distribution: Partial<Record<Attribution, number>>;
  top_attribution: Attribution | null;
}

export interface TrackProgress {
  done: number;
  total: number;
  rate: number;
}

export interface ProgressReport {
  by_track: Record<string, TrackProgress>;
  streak_days: number;
  heatmap: { date: string; count: number }[];
}

export interface PlanGenerationResult {
  plan_id: string;
  task_count: number;
  first_date: string;
}

export interface RescheduleResult {
  rescheduled: number;
  preserved_done: number;
}

export interface VocabToday {
  new_items: VocabItem[];
  review_items: VocabItem[];
}

export interface MockSubmitResult {
  estimate_score: number | null;
  by_section: Record<string, number>;
  attempt_ids: string[];
}

export interface AssessmentGapRow {
  subject: string;
  score: number;
  target: number;
  gap: number;
}

export interface AssessmentFinishResult {
  scores: AssessmentScores;
  estimate_total: number;
  gap_table: AssessmentGapRow[];
}

export interface MasteryCoverage {
  coverage: number;
  weak_top5: { point_id: string; title: string; level: MasteryLevel }[];
}

export interface ProfileCreateInput {
  track_type: ProfileTrackType;
  title: string;
  exam_date?: string;
  target_score?: number;
  subjects?: string[];
  cert_type?: CertType;
  level?: CetLevel;
  daily_minutes?: number;
}

export interface ProfilePatch {
  title?: string;
  exam_date?: string | null;
  target_score?: number | null;
  current_estimate?: number | null;
  subjects?: string[];
  daily_minutes?: number;
  status?: ProfileStatus;
}

export interface AppStatePatch {
  active_profile_id?: string | null;
  settings?: CampusSettings;
}

export interface LibraryQAInput {
  profileId: string;
  question: string;
  docId?: string;
}

export interface GenerateQuestionsInput {
  profileId: string;
  docId?: string;
  pointId?: string;
  count?: number;
}

export interface GradingSubmitInput {
  profileId: string;
  questionId?: string;
  kind: GradingKind;
  answer: string;
  rubricId?: string;
  customRubric?: string;
}

export interface MistakePatch {
  attribution?: Attribution;
  note?: string;
  resolved?: number;
  point_id?: string | null;
}

export interface QuestionCreateInput {
  profileId: string;
  subject: string;
  stem: string;
  qtype?: QuestionType;
  pointId?: string;
  options?: QuestionOption[];
  answer?: string;
  answerMeta?: Record<string, unknown>;
  maxScore?: number;
  difficulty?: number;
  source?: QuestionSource;
  docId?: string;
}

export interface QuestionPatch {
  subject?: string;
  stem?: string;
  qtype?: QuestionType;
  point_id?: string | null;
  options?: QuestionOption[] | null;
  answer?: string | null;
  answer_meta?: Record<string, unknown> | null;
  max_score?: number;
  difficulty?: number | null;
}

export interface AttemptSubmitInput {
  profileId: string;
  questionId: string;
  sessionType?: SessionType;
  mockExamId?: string;
  answer: string;
}

export interface ListPage {
  page?: number;
  pageSize?: number;
}

export interface MistakeFilters extends ListPage {
  attribution?: Attribution;
  resolved?: number;
  point_id?: string;
  track_type?: CampusTrack;
}

export interface GradingHistoryFilters extends ListPage {
  subject?: string;
  kind?: GradingKind;
}

export interface QuestionFilters extends ListPage {
  point_id?: string;
  qtype?: QuestionType;
  subject?: string;
}

export interface TaskFilters {
  date?: string;
  status?: TaskStatus;
  track?: PlanTrack;
}

export interface TaskPatch {
  status?: TaskStatus;
  scheduled_date?: string;
  priority?: number;
}

export interface SchoolProfilePatch {
  school?: string;
  major?: string;
  degree_type?: DegreeType;
  subjects?: string[];
  enroll_count?: number;
  recommend_ratio?: number;
  past_scores?: { year: number; line: number }[];
  books?: string[];
  note?: string;
}

export interface SchoolProfileExtractInput {
  profileId: string;
  text: string;
}

export interface MasteryPatch {
  pointId?: string;
  dimension?: MasteryDimension;
  level: MasteryLevel;
}

export interface DeadlineCreateInput {
  profileId: string;
  nodeType: DeadlineNodeType;
  date: string;
  isReference?: boolean;
}

export interface KnowledgePointCreateInput {
  profileId: string;
  title: string;
  parent_id?: string | null;
  desc?: string;
  order_index?: number;
}

export interface KnowledgePointPatch {
  title?: string;
  desc?: string | null;
  order_index?: number;
  parent_id?: string | null;
}

export interface KnowledgeTreeGenerateInput {
  profileId: string;
  text?: string;
  docId?: string;
}
