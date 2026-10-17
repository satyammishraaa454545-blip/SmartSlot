import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Archive, CheckCircle2, Loader2, OctagonX, ShieldCheck } from "lucide-react";
import { ApiError, errorMessage, versionsApi, type ValidateResponse, type ValidationReport, type VersionMeta } from "../../api";
import { Button, Modal } from "../../components/ui";
import { ValidationBadge } from "../../components/status/StatusBadges";
import { plural } from "../../lib/format";
import { ConflictList } from "../timetable/edit/MoveFeedback";

interface Props {
  version: VersionMeta | null;
  /** the version that is published right now (it will be archived) */
  currentlyPublished: VersionMeta | null;
  onClose: () => void;
  /** performs the publish; may throw an ApiError */
  onPublish: (version: VersionMeta, acknowledgeIncomplete: boolean) => Promise<unknown>;
}

/**
 * Confirmation before publishing: shows a fresh validation report. Hard conflicts block publishing; unscheduled
 * sessions require ticking an acknowledgement (the version is then published as INCOMPLETE).
 */
export function PublishDialog({ version, currentlyPublished, onClose, onPublish }: Props) {
  const [report, setReport] = useState<ValidateResponse | null>(null);
  const [blockedReport, setBlockedReport] = useState<ValidationReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = version?.id ?? null;

  useEffect(() => {
    setReport(null);
    setBlockedReport(null);
    setLoadError(null);
    setAck(false);
    setError(null);
    if (id === null) return;
    let cancelled = false;
    setLoading(true);
    versionsApi
      .validate(id)
      .then((r) => !cancelled && setReport(r))
      .catch((err) => !cancelled && setLoadError(errorMessage(err)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id]);

  const validation = blockedReport ?? report?.validation ?? null;
  const summary = report?.summary ?? null;
  const blocking = !!validation && !validation.valid;
  const unscheduled = summary?.unscheduled ?? 0;
  const incomplete = !blocking && unscheduled > 0;
  const canPublish = !!validation && !blocking && !busy && (!incomplete || ack);

  const publish = async () => {
    if (!version || !canPublish) return;
    setBusy(true);
    setError(null);
    try {
      await onPublish(version, incomplete && ack);
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === "PUBLISH_BLOCKED") {
        setBlockedReport((err.detail as unknown as { validation: ValidationReport }).validation);
      }
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const errors = validation?.conflicts.filter((c) => c.severity === "error") ?? [];

  return (
    <Modal
      open={!!version}
      onClose={busy ? () => undefined : onClose}
      size="md"
      title={version ? `Publish ${version.label}?` : "Publish"}
      subtitle="Publishing makes this the timetable everyone sees. The check below runs fresh, right now."
      data-testid="publish-dialog"
      footer={
        <>
          <Button onClick={onClose} disabled={busy} data-testid="publish-cancel">
            Cancel
          </Button>
          <Button variant="success" onClick={() => void publish()} disabled={!canPublish} loading={busy} icon={<ShieldCheck className="h-4 w-4" aria-hidden />} data-testid="publish-confirm">
            {incomplete ? "Publish as incomplete" : "Publish"}
          </Button>
        </>
      }
    >
      {loading && (
        <p className="flex items-center gap-2 py-4 text-slate-500" data-testid="publish-checking">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> Checking the timetable...
        </p>
      )}
      {loadError && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-800" role="alert">
          {loadError}
        </p>
      )}
      {validation && summary && version && (
        <div className="space-y-3.5" data-testid="publish-report" data-status={validation.status}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <ValidationBadge summary={{ ...summary, status: validation.status, error_count: validation.error_count }} />
            <span className="text-sm text-slate-700" data-testid="publish-summary">
              {validation.summary}
            </span>
            <span className="w-full text-xs text-slate-500">
              {summary.scheduled} of {summary.total_sessions} required sessions scheduled
              {errors.length > 0 && ` · ${plural(errors.length, "conflict")}`}
            </span>
          </div>

          {blocking && (
            <div className="space-y-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3" data-testid="publish-blocked" role="alert">
              <p className="flex items-start gap-2 font-semibold text-red-900">
                <OctagonX className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden />
                Publishing is blocked until {errors.length === 1 ? "this conflict is" : "these conflicts are"} fixed.
              </p>
              <ConflictList conflicts={errors.slice(0, 5)} />
              {errors.length > 5 && <p className="text-xs text-red-800">and {errors.length - 5} more.</p>}
              <Link to="/timetable" onClick={onClose} className="inline-block text-xs font-semibold text-indigo-700 hover:underline">
                Open the timetable to fix them
              </Link>
            </div>
          )}

          {incomplete && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950" data-testid="incomplete-warning" role="alert">
              <p className="flex items-start gap-2 font-semibold">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" aria-hidden />
                {plural(unscheduled, "required session is", "required sessions are")} still unscheduled. Publishing will mark this timetable as INCOMPLETE.
              </p>
              <label className="mt-2.5 flex cursor-pointer items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 rounded border-amber-400 text-amber-600"
                  checked={ack}
                  onChange={(e) => setAck(e.target.checked)}
                  data-testid="ack-incomplete"
                  data-autofocus
                />
                <span>I understand that {plural(unscheduled, "session")} will be missing, and I want to publish it as incomplete.</span>
              </label>
            </div>
          )}

          {!blocking && !incomplete && (
            <p className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 font-medium text-emerald-900" data-testid="publish-ready">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden /> Ready to publish: no conflicts, and every required session is scheduled.
            </p>
          )}

          {currentlyPublished && currentlyPublished.id !== version.id && (
            <p className="flex items-start gap-2 text-slate-600" data-testid="publish-archives">
              <Archive className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden />
              <span>
                <strong className="text-slate-800">{currentlyPublished.label}</strong> is published now. It will be archived, kept in the list and can always be restored.
              </span>
            </p>
          )}
          {error && !blocking && (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-800" role="alert" data-testid="publish-error">
              {error}
            </p>
          )}
        </div>
      )}
    </Modal>
  );
}
