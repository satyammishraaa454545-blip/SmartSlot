import { useState } from "react";
import { AlertTriangle, GitBranchPlus, Lock, Search, Send } from "lucide-react";
import type { VersionDetail } from "../../../api";
import { Banner, Button } from "../../../components/ui";
import { plural } from "../../../lib/format";

/** Published and archived versions are never edited in place: say so, and offer the one-click way to a draft. */
export function ReadOnlyBanner({ version, onRestore }: { version: VersionDetail; onRestore: () => Promise<unknown> }) {
  const [busy, setBusy] = useState(false);
  const published = version.status === "published";
  const run = async () => {
    setBusy(true);
    try {
      await onRestore();
    } catch {
      /* the hook already showed a toast */
    } finally {
      setBusy(false);
    }
  };
  return (
    <Banner
      tone="blue"
      icon={<Lock className="h-5 w-5 text-sky-600" aria-hidden />}
      title="This version is read-only — Restore as draft to edit"
      data-testid="readonly-banner"
      actions={
        <Button variant="primary" onClick={() => void run()} loading={busy} icon={<GitBranchPlus className="h-4 w-4" aria-hidden />} data-testid="restore-as-draft">
          Restore as draft
        </Button>
      }
    >
      {published
        ? "This is the published timetable, so it is never changed in place. Restoring makes an editable copy; the published version stays exactly as it is until you publish the copy."
        : "This is an archived version. Restoring makes an editable copy and leaves this one untouched."}
    </Banner>
  );
}

/** Classes that clash with the CURRENT availability / room data (for example a teacher became unavailable). */
export function ReviewBanner({
  version,
  onShow,
  onFix,
}: {
  version: VersionDetail;
  onShow: (entryId: string) => void;
  onFix: () => Promise<unknown>;
}) {
  const [busy, setBusy] = useState(false);
  const items = version.needs_review;
  if (items.length === 0) return null;
  const draft = version.status === "draft";
  const run = async () => {
    setBusy(true);
    try {
      await onFix();
    } catch {
      /* toast already shown */
    } finally {
      setBusy(false);
    }
  };
  return (
    <Banner
      tone="amber"
      role="alert"
      icon={<AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />}
      title={`${plural(items.length, "scheduled class", "scheduled classes")} now need${items.length === 1 ? "s" : ""} review`}
      data-testid="needs-review-banner"
      actions={
        <>
          <Button size="sm" icon={<Search className="h-4 w-4" aria-hidden />} onClick={() => onShow(items[0].entry_id)} data-testid="review-show">
            Show the first one
          </Button>
          {!draft && (
            <Button size="sm" variant="primary" icon={<GitBranchPlus className="h-4 w-4" aria-hidden />} loading={busy} onClick={() => void run()} data-testid="create-fixed-draft">
              Create fixed draft
            </Button>
          )}
          {draft && (
            <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-900">
              <Send className="h-3.5 w-3.5" aria-hidden /> Fix them, then publish
            </span>
          )}
        </>
      }
    >
      <p>Something changed after this timetable was made (a teacher or room is no longer available, or a room changed size), so these classes no longer fit:</p>
      <ul className="mt-1.5 space-y-1.5" data-testid="needs-review-list">
        {items.slice(0, 4).map((r) => (
          <li key={r.entry_id} className="rounded-lg border border-amber-200 bg-white/60 px-3 py-1.5" data-testid="needs-review-item" data-entry-id={r.entry_id}>
            <button type="button" onClick={() => onShow(r.entry_id)} className="text-left font-semibold underline decoration-amber-400 underline-offset-2 hover:decoration-amber-700">
              {r.label}
            </button>
            {r.messages[0] && <span className="block text-[13px] text-amber-950/90">{r.messages[0]}</span>}
          </li>
        ))}
        {items.length > 4 && <li className="px-1 text-[13px]">and {items.length - 4} more (see the Conflicts panel below).</li>}
      </ul>
      {!draft && (
        <p className="mt-1.5 font-medium">
          This {version.status} version is not changed. Create a fixed draft, move the flagged classes there, and publish it when it is valid.
        </p>
      )}
    </Banner>
  );
}
