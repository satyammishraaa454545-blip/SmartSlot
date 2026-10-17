import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, CalendarDays, Columns2, FilePenLine, GitBranchPlus, History, Loader2, ShieldCheck, ShieldQuestion, Sparkles, Trash2 } from "lucide-react";
import { errorMessage, versionsApi, type DatasetDetail, type ValidateResponse, type VersionMeta } from "../../api";
import { PageHeader } from "../../components/layout/PageHeader";
import { RequireDataset } from "../../components/layout/RequireDataset";
import { ValidationBadge, VersionStatusChip } from "../../components/status/StatusBadges";
import { Badge, Banner, Button, Card, CardBody, CardHeader, ConfirmDialog, EmptyState, ErrorBoundary, Skeleton, useToast } from "../../components/ui";
import { formatDateTime, plural } from "../../lib/format";
import { useApp } from "../../state/AppState";
import { ConflictList } from "../timetable/edit/MoveFeedback";
import { ComparePanel, type CompareHandle } from "./ComparePanel";
import { ExportCard } from "./ExportCard";
import { PublishDialog } from "./PublishDialog";
import { useVersionActions } from "./useVersionActions";

export function VersionsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        step={5}
        title="Publish & Versions"
        description="Every time you generate, SmartSlot saves a new draft. Publish the one you trust, compare versions to see what changed, restore an older one, and export or print the result."
      />
      <RequireDataset>
        {(dataset) => (
          <ErrorBoundary what="the versions page">
            <VersionsBody key={dataset.id} dataset={dataset} />
          </ErrorBoundary>
        )}
      </RequireDataset>
    </div>
  );
}

function VersionsBody({ dataset }: { dataset: DatasetDetail }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const { versions, versionId, version, selectVersion, refreshVersion, datasetStatus } = useApp();
  const { restoreAsDraft, publish, remove, syncLists } = useVersionActions();

  const [publishTarget, setPublishTarget] = useState<VersionMeta | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<VersionMeta | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [validating, setValidating] = useState<number | null>(null);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [checked, setChecked] = useState<Record<number, ValidateResponse>>({});
  const [freshId, setFreshId] = useState<number | null>(null);
  const compare = useRef<CompareHandle>(null);

  const published = versions.find((v) => v.status === "published") ?? null;

  // "Review & publish" on the timetable page links here with ?publish=<id>
  const wantPublish = params.get("publish");
  useEffect(() => {
    if (!wantPublish) return;
    const v = versions.find((x) => String(x.id) === wantPublish);
    if (v && v.status === "draft") setPublishTarget(v);
    if (v || datasetStatus === "ready") {
      const next = new URLSearchParams(params);
      next.delete("publish");
      setParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantPublish, versions]);

  const openInTimetable = (v: VersionMeta) => {
    selectVersion(v.id);
    navigate("/timetable");
  };

  const validateNow = async (v: VersionMeta) => {
    setValidating(v.id);
    try {
      const res = await versionsApi.validate(v.id);
      setChecked((c) => ({ ...c, [v.id]: res }));
      void syncLists();
      if (v.id === versionId) void refreshVersion();
    } catch (err) {
      toast.error("Could not validate that version", errorMessage(err));
    } finally {
      setValidating(null);
    }
  };

  const restore = async (v: VersionMeta, fixed = false) => {
    setRestoring(v.id);
    try {
      const res = await restoreAsDraft(v, { fixed });
      setFreshId(res.version.id);
      window.setTimeout(() => setFreshId(null), 4000);
    } catch {
      /* toast shown by the hook */
    } finally {
      setRestoring(null);
    }
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await remove(deleteTarget, deleteTarget.id === versionId);
      setDeleteTarget(null);
    } catch {
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const startCompare = (v: VersionMeta) => {
    // compare against the published version (or the version it was copied from), else the next one in the list
    const base = (published && published.id !== v.id ? published : null) ?? versions.find((x) => x.id === v.parent_version_id) ?? versions.find((x) => x.id !== v.id) ?? null;
    if (base) compare.current?.run(base.id, v.id);
  };

  if (datasetStatus === "loading") {
    return (
      <div className="space-y-4" aria-busy="true">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <>
      <PublishedBanner published={published} onOpen={openInTimetable} onFix={(v) => restore(v, true)} fixing={restoring === published?.id} />

      {versions.length === 0 ? (
        <Card data-testid="versions-card">
          <EmptyState
            icon={<History className="h-7 w-7" aria-hidden />}
            title="No versions yet"
            action={
              <Link to="/generate">
                <Button variant="primary" icon={<Sparkles className="h-4 w-4" aria-hidden />}>
                  Generate a timetable
                </Button>
              </Link>
            }
          >
            Generate a timetable and it will be saved here as a draft. Nothing is published until you decide to.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          <Card data-testid="versions-card" className="xl:col-start-1 xl:row-start-1">
            <CardHeader
              icon={<History className="h-5 w-5" aria-hidden />}
              title="Saved versions"
              description={`${plural(versions.length, "version")}, newest first. Generating again adds a new draft; it never changes a published version.`}
            />
            <CardBody>
              <ol className="relative space-y-4 border-l-2 border-slate-200 pl-6" data-testid="versions-list">
                {versions.map((v) => (
                  <VersionRow
                    key={v.id}
                    v={v}
                    all={versions}
                    isOpen={v.id === versionId}
                    fresh={v.id === freshId}
                    checked={checked[v.id] ?? null}
                    validating={validating === v.id}
                    restoring={restoring === v.id}
                    onView={() => openInTimetable(v)}
                    onValidate={() => void validateNow(v)}
                    onDismissCheck={() =>
                      setChecked((c) => {
                        const { [v.id]: _drop, ...rest } = c;
                        void _drop;
                        return rest;
                      })
                    }
                    onPublish={() => setPublishTarget(v)}
                    onRestore={() => void restore(v)}
                    onCompare={() => startCompare(v)}
                    onDelete={() => setDeleteTarget(v)}
                  />
                ))}
              </ol>
            </CardBody>
          </Card>
          <div className="xl:col-start-2 xl:row-span-2 xl:row-start-1">
            <ComparePanel ref={compare} versions={versions} />
          </div>
          <div className="xl:col-start-1 xl:row-start-2">
            <ExportCard dataset={dataset} versions={versions} preferredId={published?.id ?? versionId ?? versions[0]?.id ?? null} loaded={version} />
          </div>
        </div>
      )}

      <PublishDialog version={publishTarget} currentlyPublished={published} onClose={() => setPublishTarget(null)} onPublish={(v, ack) => publish(v, ack)} />
      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete this version?"
        confirmLabel="Delete version"
        danger
        busy={deleting}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleteTarget(null)}
        data-testid="delete-dialog"
        confirmTestId="delete-confirm"
      >
        {deleteTarget && (
          <p>
            <strong className="text-slate-900">{deleteTarget.label}</strong> ({deleteTarget.status_label}) will be removed for good. Other versions, including the published one, are not touched.
          </p>
        )}
      </ConfirmDialog>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------------------
function PublishedBanner({ published, onOpen, onFix, fixing }: { published: VersionMeta | null; onOpen: (v: VersionMeta) => void; onFix: (v: VersionMeta) => void; fixing: boolean }) {
  if (!published) {
    return (
      <Banner tone="blue" icon={<ShieldQuestion className="h-5 w-5 text-sky-600" aria-hidden />} title="Nothing is published yet" data-testid="published-banner" role="status">
        Publish a draft below when you are happy with it. A published timetable is never changed by regenerating; it only changes if you publish a different version.
      </Banner>
    );
  }
  const incomplete = !published.is_complete;
  const review = published.summary.needs_review_count;
  return (
    <div className="space-y-3" data-testid="published-banner" data-version-id={published.id}>
      <Banner
        tone={incomplete ? "amber" : "green"}
        icon={<ShieldCheck className={`h-6 w-6 ${incomplete ? "text-amber-600" : "text-emerald-600"}`} aria-hidden />}
        title={
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base">
            Published timetable: {published.label}
            <VersionStatusChip version={published} size="sm" />
          </span>
        }
        actions={
          <Button size="sm" icon={<CalendarDays className="h-4 w-4" aria-hidden />} onClick={() => onOpen(published)} data-testid="published-view">
            View in timetable
          </Button>
        }
      >
        <p>
          Published {formatDateTime(published.published_at)} · {published.summary.scheduled} of {published.summary.total_sessions} sessions scheduled
          {incomplete && <strong> · INCOMPLETE ({plural(published.summary.unscheduled, "session")} missing)</strong>}
        </p>
        <p className="mt-0.5">
          <strong>Regenerating never overwrites it.</strong> New runs and edits only create or change drafts; the published version changes only when you publish another one.
        </p>
      </Banner>
      {review > 0 && (
        <Banner
          tone="amber"
          role="alert"
          icon={<AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />}
          title={`${plural(review, "scheduled class", "scheduled classes")} in the published timetable now need${review === 1 ? "s" : ""} review`}
          data-testid="published-needs-review"
          actions={
            <Button size="sm" variant="primary" icon={<GitBranchPlus className="h-4 w-4" aria-hidden />} loading={fixing} onClick={() => onFix(published)} data-testid="create-fixed-draft">
              Create fixed draft
            </Button>
          }
        >
          A teacher or room became unavailable after publishing. The published timetable is left exactly as it is; create a fixed draft, move the flagged classes, and publish it.
        </Banner>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
interface RowProps {
  v: VersionMeta;
  all: VersionMeta[];
  isOpen: boolean;
  fresh: boolean;
  checked: ValidateResponse | null;
  validating: boolean;
  restoring: boolean;
  onView: () => void;
  onValidate: () => void;
  onDismissCheck: () => void;
  onPublish: () => void;
  onRestore: () => void;
  onCompare: () => void;
  onDelete: () => void;
}

const DOT: Record<VersionMeta["status"], string> = {
  published: "bg-emerald-500",
  draft: "bg-sky-500",
  archived: "bg-slate-400",
};

function VersionRow({ v, all, isOpen, fresh, checked, validating, restoring, onView, onValidate, onDismissCheck, onPublish, onRestore, onCompare, onDelete }: RowProps) {
  const parent = v.parent_version_id !== null ? all.find((x) => x.id === v.parent_version_id) : null;
  const s = v.summary;
  const complete = s.unscheduled === 0;
  const errors = checked?.validation.conflicts.filter((c) => c.severity === "error") ?? [];

  return (
    <li
      className="relative"
      data-testid={`version-row-${v.id}`}
      data-version-id={v.id}
      data-status={v.status}
      data-label={v.label}
      data-complete={complete}
    >
      <span className={`absolute -left-[33px] top-4 h-3 w-3 rounded-full ring-4 ring-white ${DOT[v.status]}`} aria-hidden />
      <div
        className={`rounded-xl border px-4 py-3.5 transition-colors ${fresh ? "border-indigo-400 bg-indigo-50/60" : v.status === "published" ? "border-emerald-300 bg-emerald-50/40" : isOpen ? "border-indigo-200 bg-indigo-50/30" : "border-slate-200 bg-white"}`}
      >
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
          <h3 className="text-[15px] font-semibold text-slate-900" data-testid="version-label">
            {v.label}
          </h3>
          <VersionStatusChip version={v} size="sm" />
          <ValidationBadge summary={s} size="sm" />
          <Badge tone={complete ? "green" : "amber"} size="sm" data-testid="completeness-chip">
            {complete ? "Complete" : "Incomplete"}
          </Badge>
          {isOpen && (
            <Badge tone="indigo" size="sm">
              Open in timetable
            </Badge>
          )}
          <span className="ml-auto text-xs text-slate-500">{formatDateTime(v.created_at)}</span>
        </div>

        <p className="mt-1.5 text-sm text-slate-600">
          <span className="tabular-nums">
            {s.scheduled} / {s.total_sessions}
          </span>{" "}
          scheduled
          {s.unscheduled > 0 && <span className="text-amber-700"> · {s.unscheduled} unscheduled</span>}
          {s.error_count > 0 && <span className="font-medium text-red-700"> · {plural(s.error_count, "conflict")}</span>}
          {s.needs_review_count > 0 && <span className="font-medium text-amber-700"> · {s.needs_review_count} need review</span>}
          <span className="text-slate-400">
            {" · "}
            {v.source === "restored" ? (parent ? `restored from ${parent.label}` : "restored copy") : "generated"} by {v.created_by}
          </span>
        </p>
        {v.notes && <p className="mt-0.5 text-xs text-slate-500">{v.notes}</p>}

        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" icon={<CalendarDays className="h-4 w-4" aria-hidden />} onClick={onView} data-testid="view-in-timetable">
            View in timetable
          </Button>
          <Button size="sm" icon={validating ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ShieldCheck className="h-4 w-4" aria-hidden />} onClick={onValidate} disabled={validating} data-testid="validate-version">
            Validate now
          </Button>
          {v.status === "draft" && (
            <Button size="sm" variant="primary" icon={<FilePenLine className="h-4 w-4" aria-hidden />} onClick={onPublish} data-testid="publish-version">
              Publish...
            </Button>
          )}
          <Button size="sm" icon={<GitBranchPlus className="h-4 w-4" aria-hidden />} onClick={onRestore} loading={restoring} data-testid="restore-version" title="Make an editable copy of this version">
            {v.status === "draft" ? "Copy as new draft" : "Restore as draft"}
          </Button>
          <Button size="sm" icon={<Columns2 className="h-4 w-4" aria-hidden />} onClick={onCompare} disabled={all.length < 2} data-testid="compare-version">
            Compare
          </Button>
          {v.status !== "published" && (
            <Button size="sm" variant="ghost" className="text-red-700 hover:bg-red-50" icon={<Trash2 className="h-4 w-4" aria-hidden />} onClick={onDelete} data-testid="delete-version">
              Delete
            </Button>
          )}
        </div>

        {checked && (
          <div
            className={`mt-3 rounded-lg border px-3 py-2.5 text-sm ${checked.validation.valid ? (checked.validation.complete ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900") : "border-red-200 bg-red-50 text-red-900"}`}
            data-testid="validation-result"
            data-status={checked.validation.status}
            role="status"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="font-medium">Checked just now: {checked.validation.summary}</p>
              <button onClick={onDismissCheck} className="shrink-0 text-xs font-semibold underline">
                Hide
              </button>
            </div>
            {errors.length > 0 && (
              <div className="mt-2">
                <ConflictList conflicts={errors.slice(0, 4)} />
                {errors.length > 4 && <p className="mt-1 text-xs">and {errors.length - 4} more. Open the timetable to see them all.</p>}
              </div>
            )}
          </div>
        )}
      </div>
    </li>
  );
}
