import { AlertTriangle, Archive, CheckCircle2, FileEdit, ShieldCheck, XCircle } from "lucide-react";
import type { Summary, ValidationStatus, VersionMeta } from "../../api";
import { Badge, type Tone } from "../ui";
import { plural } from "../../lib/format";

/** Draft / Published / Published (incomplete) / Archived chip. Uses the server-provided `status_label`. */
export function VersionStatusChip({ version, size = "md" }: { version: Pick<VersionMeta, "status" | "status_label">; size?: "sm" | "md" }) {
  const map: Record<VersionMeta["status"], { tone: Tone; icon: JSX.Element }> = {
    draft: { tone: "blue", icon: <FileEdit className="h-3.5 w-3.5" aria-hidden /> },
    published: { tone: "green", icon: <ShieldCheck className="h-3.5 w-3.5" aria-hidden /> },
    archived: { tone: "slate", icon: <Archive className="h-3.5 w-3.5" aria-hidden /> },
  };
  const m = map[version.status];
  // "Published (incomplete)" deserves the amber warning colour.
  const tone: Tone = version.status === "published" && version.status_label !== "Published" ? "amber" : m.tone;
  return (
    <Badge tone={tone} icon={m.icon} size={size} data-testid="version-status-chip">
      {version.status_label}
    </Badge>
  );
}

interface ValidationBadgeProps {
  summary: Summary;
  size?: "sm" | "md";
  /** show the one-sentence explanation next to the badge */
  withMessage?: boolean;
}

export function validationLabel(summary: Pick<Summary, "status" | "unscheduled" | "error_count">): string {
  switch (summary.status) {
    case "valid_complete":
      return "Valid · Complete";
    case "valid_incomplete":
      return `Valid · ${summary.unscheduled} unscheduled`;
    default:
      return plural(summary.error_count, "conflict");
  }
}

export const validationTone = (status: ValidationStatus): Tone =>
  status === "valid_complete" ? "green" : status === "valid_incomplete" ? "amber" : "red";

/** The always-visible validation status: green Valid - Complete / amber Valid - N unscheduled / red N conflicts. */
export function ValidationBadge({ summary, size = "md", withMessage = false }: ValidationBadgeProps) {
  const tone = validationTone(summary.status);
  const icon =
    summary.status === "valid_complete" ? (
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
    ) : summary.status === "valid_incomplete" ? (
      <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
    ) : (
      <XCircle className="h-3.5 w-3.5" aria-hidden />
    );
  return (
    <span className="inline-flex items-center gap-2" title={summary.message}>
      <Badge tone={tone} icon={icon} size={size} data-testid="validation-badge" data-status={summary.status}>
        {validationLabel(summary)}
      </Badge>
      {withMessage && <span className="text-sm text-slate-600">{summary.message}</span>}
    </span>
  );
}
