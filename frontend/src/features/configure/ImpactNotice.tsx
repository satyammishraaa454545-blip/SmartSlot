import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CalendarDays, CheckCircle2, GitBranchPlus } from "lucide-react";
import type { VersionMeta } from "../../api";
import { Banner, Button } from "../../components/ui";
import { plural } from "../../lib/format";
import { useApp } from "../../state/AppState";
import { useVersionActions } from "../versions/useVersionActions";

/**
 * After availability changes: how many scheduled classes in the existing draft / published timetables no longer fit.
 * The counts come from the live validation of each version, so nothing is ever modified here. A published version is
 * never changed; the way forward is a fixed draft.
 */
export function ImpactNotice() {
  const { versions, selectVersion } = useApp();
  const { restoreAsDraft } = useVersionActions();
  const navigate = useNavigate();
  const [busy, setBusy] = useState<number | null>(null);

  const live = versions.filter((v) => v.status !== "archived");
  if (live.length === 0) return null;
  const affected = live.filter((v) => v.summary.needs_review_count > 0);

  if (affected.length === 0) {
    return (
      <p className="flex items-center gap-2 text-sm text-emerald-800" data-testid="availability-impact-ok">
        <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden /> Your existing timetables still fit this availability: no scheduled class needs review.
      </p>
    );
  }

  const open = (v: VersionMeta) => {
    selectVersion(v.id);
    navigate("/timetable");
  };
  const fix = async (v: VersionMeta) => {
    setBusy(v.id);
    try {
      await restoreAsDraft(v, { fixed: true, goToTimetable: true });
    } catch {
      /* toast already shown */
    } finally {
      setBusy(null);
    }
  };

  const most = Math.max(...affected.map((v) => v.summary.needs_review_count));
  // the published version first, then the newest drafts
  const ordered = [...affected].sort((a, b) => Number(b.status === "published") - Number(a.status === "published") || b.id - a.id);

  return (
    <Banner
      tone="amber"
      role="status"
      icon={<AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />}
      title={`${plural(most, "scheduled class", "scheduled classes")} now need${most === 1 ? "s" : ""} review`}
      data-testid="availability-impact"
      className="w-full"
    >
      <p>This change leaves existing timetables untouched, but some classes no longer fit it:</p>
      <ul className="mt-2 divide-y divide-amber-200/70 rounded-lg border border-amber-200 bg-white/60">
        {ordered.map((v) => {
          const n = v.summary.needs_review_count;
          const published = v.status === "published";
          return (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 px-3 py-2" data-testid="availability-impact-item" data-version-id={v.id} data-status={v.status}>
              <span className="min-w-0 text-sm">
                <strong>{published ? "Published" : "Draft"}: {v.label}</strong>
                <span className="text-amber-900/80"> · {plural(n, "class", "classes")} flagged{published ? ", left exactly as it is" : ""}</span>
              </span>
              <span className="flex shrink-0 items-center gap-2">
                <Button size="sm" icon={<CalendarDays className="h-4 w-4" aria-hidden />} onClick={() => open(v)} data-testid="impact-open">
                  Open timetable
                </Button>
                {published && (
                  <Button size="sm" variant="primary" icon={<GitBranchPlus className="h-4 w-4" aria-hidden />} loading={busy === v.id} onClick={() => void fix(v)} data-testid="create-fixed-draft">
                    Create fixed draft
                  </Button>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Banner>
  );
}
