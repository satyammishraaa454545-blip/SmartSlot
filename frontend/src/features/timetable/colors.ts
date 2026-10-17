// Stable colour per subject. The colour is chosen from the subject's position in the dataset's subject list, so
// it never changes between views, versions or reloads (and subjects get distinct hues before any colour repeats).

export interface SubjectColor {
  /** soft fill for the class block */
  bg: string;
  /** strong accent (left edge, legend dot) */
  accent: string;
  /** dark text with AA contrast on `bg` */
  text: string;
  /** secondary text on `bg` */
  muted: string;
}

const PALETTE: SubjectColor[] = [
  { bg: "#eef2ff", accent: "#6366f1", text: "#1e1b4b", muted: "#4338ca" }, // indigo
  { bg: "#ecfdf5", accent: "#10b981", text: "#022c22", muted: "#047857" }, // emerald
  { bg: "#fff7ed", accent: "#f97316", text: "#431407", muted: "#c2410c" }, // orange
  { bg: "#f0f9ff", accent: "#0ea5e9", text: "#082f49", muted: "#0369a1" }, // sky
  { bg: "#fdf2f8", accent: "#ec4899", text: "#500724", muted: "#be185d" }, // pink
  { bg: "#f7fee7", accent: "#84cc16", text: "#1a2e05", muted: "#4d7c0f" }, // lime
  { bg: "#f5f3ff", accent: "#8b5cf6", text: "#2e1065", muted: "#6d28d9" }, // violet
  { bg: "#fffbeb", accent: "#eab308", text: "#422006", muted: "#a16207" }, // yellow
  { bg: "#f0fdfa", accent: "#14b8a6", text: "#042f2e", muted: "#0f766e" }, // teal
  { bg: "#fef2f2", accent: "#f43f5e", text: "#4c0519", muted: "#be123c" }, // rose
];

const FALLBACK: SubjectColor = { bg: "#f1f5f9", accent: "#64748b", text: "#0f172a", muted: "#475569" };

function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Build a lookup from subject id to colour; unknown subjects get a stable hashed colour. */
export function makeColorOf(subjectIds: string[]): (subjectId: string) => SubjectColor {
  const index = new Map(subjectIds.map((id, i) => [id, i]));
  return (subjectId: string) => {
    if (!subjectId) return FALLBACK;
    const i = index.get(subjectId);
    return PALETTE[(i ?? hash(subjectId)) % PALETTE.length];
  };
}
