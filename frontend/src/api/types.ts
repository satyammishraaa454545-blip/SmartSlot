// TypeScript mirror of docs/API.md section 3. Keep field names identical to the server JSON.

export type Day = "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun";
export const ALL_DAYS: Day[] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const DAY_NAMES: Record<Day, string> = {
  Mon: "Monday",
  Tue: "Tuesday",
  Wed: "Wednesday",
  Thu: "Thursday",
  Fri: "Friday",
  Sat: "Saturday",
  Sun: "Sunday",
};

export type VersionStatus = "draft" | "published" | "archived";
export type ValidationStatus = "valid_complete" | "valid_incomplete" | "invalid";
export type SessionType = "lecture" | "practical";
export type RoomType = "classroom" | "lab";

// ---------- records ----------
export interface Teacher {
  teacher_id: string;
  name: string;
  department_id: string;
}
export interface Subject {
  subject_id: string;
  name: string;
  department_id: string;
  session_type: SessionType;
}
export interface Batch {
  batch_id: string;
  name: string;
  semester: string;
  student_count: number;
  department_id: string;
}
export interface Room {
  room_id: string;
  name: string;
  capacity: number;
  room_type: RoomType;
}
export interface Requirement {
  subject_id: string;
  batch_id: string;
  teacher_id: string;
  sessions_per_week: number;
  duration: number;
}
export interface PeriodDef {
  period: number;
  start: string;
  end: string;
  is_break: boolean;
}
export interface AvailabilityRule {
  resource_id: string;
  day: Day;
  period: number;
  available: false;
}

// ---------- import ----------
export interface ImportIssue {
  severity: "error" | "warning";
  file: string | null;
  row: number | null;
  field: string | null;
  value: string | null;
  code: string;
  message: string;
  how_to_fix: string;
}
export interface FileSummary {
  file: string;
  key: string;
  required: boolean;
  present: boolean;
  rows: number;
  accepted: number;
  rejected: number;
  errors: number;
  warnings: number;
}
export interface ImportReport {
  status: "ok" | "has_errors";
  error_count: number;
  warning_count: number;
  total_sessions: number;
  counts: Record<string, number>;
  files: FileSummary[];
  issues: ImportIssue[];
  truncated: boolean;
}

// ---------- datasets ----------
export interface DatasetSummary {
  id: number;
  name: string;
  semester: string;
  source: string;
  import_status: "ok" | "has_errors";
  created_at: string;
  updated_at: string;
  counts: Record<string, number>;
  error_count: number;
  warning_count: number;
  total_sessions: number;
  version_count: number;
  published_version_id: number | null;
}
export interface DatasetDetail extends DatasetSummary {
  import_report: ImportReport;
  teachers: Teacher[];
  subjects: Subject[];
  batches: Batch[];
  rooms: Room[];
  requirements: Requirement[];
  days: Day[];
  periods: PeriodDef[];
  teaching_periods: number[];
  availability: AvailabilityRule[];
}
export interface ImportResponse {
  dataset: DatasetSummary;
  import_report: ImportReport;
  can_generate: boolean;
}
export interface DatasetEditResponse {
  dataset: DatasetDetail;
  warnings: string[];
}

// ---------- timetable ----------
export interface Entry {
  entry_id: string;
  session_id: string;
  day: Day;
  start_period: number;
  end_period: number;
  duration: number;
  start_time: string | null;
  end_time: string | null;
  subject_id: string;
  subject_name: string;
  subject_type: SessionType;
  batch_id: string;
  batch_name: string;
  teacher_id: string;
  teacher_name: string;
  room_id: string;
  room_name: string;
  room_type: RoomType | "";
  needs_review: boolean;
  review_messages: string[];
}
export interface Suggestion {
  day: Day;
  start_period: number;
  end_period: number;
  duration: number;
  start_time: string | null;
  end_time: string | null;
  room_id: string;
  room_name: string;
  teacher_id: string | null;
  teacher_name: string | null;
  label: string;
}
export type ConflictCode =
  | "TEACHER_OVERLAP"
  | "ROOM_OVERLAP"
  | "BATCH_OVERLAP"
  | "TEACHER_UNAVAILABLE"
  | "ROOM_UNAVAILABLE"
  | "ROOM_CAPACITY"
  | "ROOM_TYPE"
  | "INVALID_DURATION"
  | "OUTSIDE_WORKING_HOURS"
  | "BLOCKED_PERIOD"
  | "INVALID_REFERENCE"
  | "MISSING_SESSION";
export interface Conflict {
  code: ConflictCode;
  severity: "error" | "warning";
  message: string;
  day: Day | null;
  period: number | null;
  entry_ids: string[];
  involved: {
    teacher_id: string | null;
    room_id: string | null;
    batch_id: string | null;
    subject_id: string | null;
  };
  suggestions: Suggestion[];
  suggested_entry_id: string | null;
}
export interface ValidationReport {
  valid: boolean;
  complete: boolean;
  status: ValidationStatus;
  error_count: number;
  warning_count: number;
  counts: Record<string, number>;
  summary: string;
  conflicts: Conflict[];
}
export interface UnscheduledItem {
  session_id: string;
  subject_id: string;
  subject_name: string;
  subject_type: string;
  batch_id: string;
  batch_name: string;
  teacher_id: string;
  teacher_name: string;
  duration: number;
  index: number;
  of: number;
  reasons: string[];
  reason_codes: string[];
  hints: string[];
}
export interface ReviewItem {
  entry_id: string;
  label: string;
  codes: string[];
  messages: string[];
}
export interface Summary {
  total_sessions: number;
  scheduled: number;
  unscheduled: number;
  status: ValidationStatus;
  error_count: number;
  warning_count: number;
  needs_review_count: number;
  message: string;
}
export interface VersionMeta {
  id: number;
  dataset_id: number;
  seq: number;
  status: VersionStatus;
  status_label: "Draft" | "Published" | "Published (incomplete)" | "Archived";
  label: string;
  source: "generated" | "restored";
  created_at: string;
  created_by: string;
  published_at: string | null;
  is_complete: boolean;
  parent_version_id: number | null;
  notes: string;
  summary: Summary;
}
export interface SearchStats {
  nodes: number;
  elapsed_ms: number;
  hit_limit: boolean;
  exhausted: boolean;
  max_nodes: number;
  time_limit_s: number;
  total_sessions: number;
  scheduled_count: number;
}
export interface GenerationResult {
  status: "complete" | "partial" | "failed";
  message: string;
  findings: string[];
  stats: SearchStats;
}
export interface VersionDetail extends VersionMeta {
  entries: Entry[];
  unscheduled: UnscheduledItem[];
  validation: ValidationReport;
  needs_review: ReviewItem[];
  dataset: { id: number; name: string; semester: string; days: Day[]; periods: PeriodDef[] };
  generation: GenerationResult | null;
}

export interface GenerateRequest {
  max_nodes?: number;
  time_limit_s?: number;
  label?: string;
  notes?: string;
  created_by?: string;
}
export interface GenerateResponse {
  version: VersionDetail;
  result: GenerationResult;
}

// ---------- editing (used by Phase 4) ----------
export interface MoveResult {
  valid: boolean;
  message: string;
  entry: Entry | null;
  conflicts: Conflict[];
  affected_entries: Entry[];
  suggestions: Suggestion[];
}
export interface EditResponse {
  message: string;
  entry: Entry | null;
  version: VersionDetail;
}
export interface ValidateResponse {
  version_id: number;
  summary: Summary;
  validation: ValidationReport;
  needs_review: ReviewItem[];
}
export interface PublishResponse {
  version: VersionDetail;
  archived_version_id: number | null;
  message: string;
}
export interface RestoreResponse {
  version: VersionDetail;
  message: string;
}

// ---------- config requests ----------
export interface PeriodInput {
  period: number;
  start: string;
  end: string;
  is_break?: boolean;
}
export interface AvailabilityChange {
  resource_id: string;
  day: Day;
  period: number;
  available: boolean;
}

export type ViewKind = "batch" | "teacher" | "room";

// ---------- compare / analytics (used by Phase 4) ----------
export interface Change {
  type: "added" | "removed" | "moved" | "room_changed" | "teacher_changed" | "changed";
  aspects: ("moved" | "room_changed" | "teacher_changed")[];
  session_id: string;
  subject_id: string;
  subject_name: string;
  batch_id: string;
  batch_name: string;
  text: string;
  before: Entry | null;
  after: Entry | null;
}
export interface CompareVersionRef {
  id: number;
  label: string;
  status: VersionStatus;
  status_label: string;
}
export interface CompareResult {
  from_version: CompareVersionRef;
  to_version: CompareVersionRef;
  summary: {
    added: number;
    removed: number;
    moved: number;
    room_changed: number;
    teacher_changed: number;
    unchanged: number;
    changed_total: number;
  };
  changes: Change[];
}
export interface Analytics {
  version_id: number;
  teachers: {
    teacher_id: string;
    name: string;
    sessions: number;
    periods_per_week: number;
    per_day: Record<string, number>;
    available_periods: number;
    utilization_pct: number;
  }[];
  rooms: {
    room_id: string;
    name: string;
    room_type: string;
    periods_used: number;
    available_periods: number;
    utilization_pct: number;
    per_day: Record<string, number>;
  }[];
  batches: {
    batch_id: string;
    name: string;
    sessions: number;
    periods_per_week: number;
    per_day: Record<string, number>;
    teaching_periods: number;
    utilization_pct: number;
  }[];
  total_periods_scheduled: number;
  teaching_periods_per_week: number;
}
export interface MoveRequest {
  day?: Day;
  start_period?: number;
  room_id?: string;
  teacher_id?: string;
}
export interface PlaceRequest {
  day: Day;
  start_period: number;
  room_id: string;
  teacher_id?: string;
}
