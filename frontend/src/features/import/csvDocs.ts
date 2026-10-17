// Plain-language documentation of the CSV template (mirrors sample_data/README.md).

export interface CsvColumn {
  name: string;
  required: boolean;
  note: string;
}

export interface CsvFileDoc {
  /** file name the importer looks for */
  file: string;
  /** key used by the API (`counts`, `files[].key`) */
  key: string;
  required: boolean;
  summary: string;
  columns: CsvColumn[];
}

export const CSV_FILES: CsvFileDoc[] = [
  {
    file: "teachers.csv",
    key: "teachers",
    required: true,
    summary: "One row per teacher.",
    columns: [
      { name: "teacher_id", required: true, note: "Unique, e.g. T01" },
      { name: "name", required: true, note: "Shown in the timetable, e.g. Dr. Sharma" },
      { name: "department_id", required: false, note: "e.g. CE" },
    ],
  },
  {
    file: "subjects.csv",
    key: "subjects",
    required: true,
    summary: "One row per subject.",
    columns: [
      { name: "subject_id", required: true, note: "Unique, e.g. CS201" },
      { name: "name", required: true, note: "e.g. Data Structures" },
      { name: "department_id", required: false, note: "" },
      { name: "session_type", required: true, note: "lecture (classroom) or practical (lab)" },
    ],
  },
  {
    file: "batches.csv",
    key: "batches",
    required: true,
    summary: "One row per student batch (class section).",
    columns: [
      { name: "batch_id", required: true, note: "Unique, e.g. CE-A" },
      { name: "name", required: true, note: "Shown in the timetable" },
      { name: "semester", required: false, note: "e.g. 3" },
      { name: "student_count", required: true, note: "Whole number; the room must seat this many" },
      { name: "department_id", required: false, note: "" },
    ],
  },
  {
    file: "rooms.csv",
    key: "rooms",
    required: true,
    summary: "One row per room.",
    columns: [
      { name: "room_id", required: true, note: "Unique, e.g. R101 or LAB1" },
      { name: "name", required: true, note: "e.g. Room 101" },
      { name: "capacity", required: true, note: "Number of seats" },
      { name: "room_type", required: true, note: "classroom or lab" },
    ],
  },
  {
    file: "requirements.csv",
    key: "requirements",
    required: true,
    summary: "What must be taught each week: one row per subject, batch and teacher.",
    columns: [
      { name: "subject_id", required: true, note: "Must exist in subjects.csv" },
      { name: "batch_id", required: true, note: "Must exist in batches.csv" },
      { name: "teacher_id", required: true, note: "Must exist in teachers.csv" },
      { name: "sessions_per_week", required: true, note: "How many sessions to place each week" },
      { name: "duration", required: false, note: "Consecutive periods per session (default 1; labs are usually 2)" },
    ],
  },
  {
    file: "days.csv",
    key: "days",
    required: true,
    summary: "The working days, one per row.",
    columns: [{ name: "day", required: true, note: "Mon, Tue, Wed, Thu, Fri, Sat or Sun" }],
  },
  {
    file: "periods.csv",
    key: "periods",
    required: true,
    summary: "The time grid. A break (for example lunch) is its own numbered period.",
    columns: [
      { name: "period", required: true, note: "1, 2, 3 ... in time order" },
      { name: "start", required: true, note: "24-hour HH:MM, e.g. 09:00" },
      { name: "end", required: true, note: "Later than start" },
      { name: "is_break", required: false, note: "1 for a break, otherwise 0" },
    ],
  },
  {
    file: "availability.csv",
    key: "availability",
    required: false,
    summary: "Optional. The slots when a teacher or room is NOT available; everything else is free.",
    columns: [
      { name: "resource_id", required: true, note: "A teacher_id or room_id" },
      { name: "day", required: true, note: "Must be listed in days.csv" },
      { name: "period", required: true, note: "Must exist in periods.csv" },
      { name: "available", required: true, note: "0 = not available (the usual value)" },
    ],
  },
];

export const CSV_FILE_NAMES = new Set(CSV_FILES.map((f) => f.file));
export const REQUIRED_FILES = CSV_FILES.filter((f) => f.required).map((f) => f.file);

export const COUNT_LABELS: { key: string; label: string }[] = [
  { key: "teachers", label: "Teachers" },
  { key: "subjects", label: "Subjects" },
  { key: "batches", label: "Batches" },
  { key: "rooms", label: "Rooms" },
  { key: "requirements", label: "Requirements" },
  { key: "days", label: "Working days" },
  { key: "periods", label: "Periods" },
  { key: "availability", label: "Unavailable slots" },
];
