import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, DoorOpen, Printer, Send, Sparkles, UserRound, Users } from "lucide-react";
import type { DatasetDetail, VersionDetail, VersionMeta, ViewKind } from "../../api";
import { PageHeader } from "../../components/layout/PageHeader";
import { RequireDataset } from "../../components/layout/RequireDataset";
import { VersionStatusChip, ValidationBadge, validationTone } from "../../components/status/StatusBadges";
import { Banner, Button, Card, EmptyState, ErrorBoundary, PageLoading, Segmented, Skeleton } from "../../components/ui";
import { TONES } from "../../components/ui/tones";
import { useApp } from "../../state/AppState";
import { formatDateTime, plural } from "../../lib/format";
import { readStorage, writeStorage } from "../../lib/storage";
import { PrintSheet } from "../print/PrintSheet";
import { useVersionActions } from "../versions/useVersionActions";
import { makeColorOf } from "./colors";
import { useTimetableEditor } from "./edit/useTimetableEditor";
import { ReadOnlyBanner, ReviewBanner } from "./edit/VersionBanners";
import { entityOptions } from "./entities";
import { EntryDrawer } from "./EntryDrawer";
import { entriesForView, unavailableSlots } from "./gridModel";
import { ConflictsPanel, UnscheduledPanel } from "./Panels";
import { TimetableGrid } from "./TimetableGrid";

const VIEWS: ViewKind[] = ["batch", "teacher", "room"];
const isView = (v: string | null): v is ViewKind => v !== null && (VIEWS as string[]).includes(v);

export function TimetablePage() {
  return (
    <div className="space-y-5">
      <PageHeader
        step={4}
        title="Timetable"
        description="Review the weekly timetable by batch, teacher or room. In a draft you can drag a class to another slot or use Edit session; every change is checked before it is saved."
      />
      <RequireDataset>{(dataset) => <TimetableBody key={dataset.id} dataset={dataset} />}</RequireDataset>
    </div>
  );
}

function TimetableBody({ dataset }: { dataset: DatasetDetail }) {
  const { versions, versionId, version, versionStatus, versionError, selectVersion, refreshVersion, datasetStatus } = useApp();
  const [params, setParams] = useSearchParams();

  // ---- which view / entity (URL first, then last used, then defaults) ----
  const storedView = readStorage("smartslot.tt.view");
  const view: ViewKind = isView(params.get("view")) ? (params.get("view") as ViewKind) : isView(storedView) ? storedView : "batch";
  const options = useMemo(() => entityOptions(dataset, view), [dataset, view]);
  const wanted = params.get("id") ?? readStorage(`smartslot.tt.entity.${view}`);
  const entity = options.find((o) => o.id === wanted) ?? options[0] ?? null;

  const go = useCallback(
    (nextView: ViewKind, nextId?: string) => {
      writeStorage("smartslot.tt.view", nextView);
      if (nextId) writeStorage(`smartslot.tt.entity.${nextView}`, nextId);
      const p = new URLSearchParams();
      p.set("view", nextView);
      if (nextId) p.set("id", nextId);
      setParams(p, { replace: true });
    },
    [setParams],
  );

  // ---- empty / loading / error states ----
  if (datasetStatus === "ready" && versions.length === 0) {
    return (
      <Card data-testid="no-versions">
        <EmptyState
          icon={<Sparkles className="h-7 w-7" aria-hidden />}
          title="No timetable yet"
          action={
            <Link to="/generate">
              <Button variant="primary" icon={<Sparkles className="h-4 w-4" aria-hidden />}>
                Generate a timetable
              </Button>
            </Link>
          }
        >
          This dataset has not been scheduled yet. Generate a timetable and it will appear here as a draft you can review.
        </EmptyState>
      </Card>
    );
  }
  if (versionStatus === "error") {
    return (
      <Banner tone="red" role="alert" title="This timetable could not be loaded" actions={<Button onClick={() => void refreshVersion()}>Try again</Button>}>
        {versionError}
      </Banner>
    );
  }
  if (!version || version.dataset_id !== dataset.id || versionStatus === "loading") {
    return (
      <div className="space-y-4" aria-busy="true" data-testid="timetable-loading">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-[28rem] w-full" />
        <PageLoading label="Loading timetable..." />
      </div>
    );
  }

  return (
    <ErrorBoundary what="the timetable">
      <LoadedTimetable
        dataset={dataset}
        version={version}
        versions={versions}
        versionId={versionId}
        selectVersion={selectVersion}
        view={view}
        options={options}
        entity={entity}
        go={go}
      />
    </ErrorBoundary>
  );
}

interface LoadedProps {
  dataset: DatasetDetail;
  version: VersionDetail;
  versions: VersionMeta[];
  versionId: number | null;
  selectVersion: (id: number | null) => void;
  view: ViewKind;
  options: ReturnType<typeof entityOptions>;
  entity: ReturnType<typeof entityOptions>[number] | null;
  go: (view: ViewKind, id?: string) => void;
}

function LoadedTimetable({ dataset, version, versions, versionId, selectVersion, view, options, entity, go }: LoadedProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [printing, setPrinting] = useState(false);
  const { restoreAsDraft } = useVersionActions();
  const colorOf = useMemo(() => makeColorOf(dataset.subjects.map((s) => s.subject_id)), [dataset.subjects]);

  const clearSelection = useCallback(() => setSelectedId(null), []);
  const editor = useTimetableEditor({ version, dataset, go, view, entityId: entity?.id ?? "", clearSelection });

  const { entries, validation, summary } = version;
  const { days, periods } = version.dataset;
  const viewEntries = entity ? entriesForView(entries, view, entity.id) : [];
  const periodsPerWeek = viewEntries.reduce((n, e) => n + e.duration, 0);
  const firstError = validation.conflicts.find((c) => c.severity === "error") ?? null;
  const conflictIds = new Set(validation.conflicts.filter((c) => c.severity === "error").flatMap((c) => c.entry_ids));
  const reviewIds = new Set(version.needs_review.map((r) => r.entry_id));
  const subjectsInView = Array.from(new Map(viewEntries.map((e) => [e.subject_id, e.subject_name])));
  const unavailable = entity && view !== "batch" ? unavailableSlots(dataset.availability, entity.id, entity.name) : [];
  const selected = selectedId ? (entries.find((e) => e.entry_id === selectedId) ?? null) : null;

  const step = (dir: 1 | -1) => {
    if (!entity || options.length < 2) return;
    const i = options.findIndex((o) => o.id === entity.id);
    go(view, options[(i + dir + options.length) % options.length].id);
  };
  const tone = TONES[validationTone(summary.status)];

  return (
    <>
      {!editor.editable && <ReadOnlyBanner version={version} onRestore={() => restoreAsDraft(version)} />}
      <ReviewBanner
        version={version}
        onShow={(entryId) => {
          const e = entries.find((x) => x.entry_id === entryId);
          if (e) {
            editor.showEntry(e, validation.conflicts);
            setSelectedId(e.entry_id);
          }
        }}
        onFix={() => restoreAsDraft(version, { fixed: true })}
      />

      {editor.lastChangeCard}

      <Card className="overflow-hidden" data-testid="timetable-card" data-version-id={version.id} data-version-status={version.status} data-editable={editor.editable}>
        {/* version + always-visible validation status */}
        <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-3 py-3 lg:px-5 ${tone.soft}`} data-testid="status-strip">
          <ValidationBadge summary={summary} />
          <div className="min-w-0 flex-1 text-sm">
            <p className="font-medium" data-testid="validation-message">
              {summary.message}
            </p>
            {summary.status === "invalid" && firstError && (
              <p className="mt-0.5 opacity-90" data-testid="validation-first-conflict">
                For example: {firstError.message}
              </p>
            )}
          </div>
          <a href="#unscheduled-title" className={`text-xs font-semibold underline ${summary.unscheduled > 0 ? "" : "hidden"}`}>
            {plural(summary.unscheduled, "unscheduled session")}
          </a>
          {editor.editable && (
            <Link to={`/versions?publish=${version.id}`} className="no-print">
              <Button size="sm" variant="primary" icon={<Send className="h-4 w-4" aria-hidden />} data-testid="goto-publish">
                Review &amp; publish
              </Button>
            </Link>
          )}
        </div>

        <div className="no-print flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-slate-100 px-3 py-3 lg:px-5">
          <Segmented<ViewKind>
            label="Timetable view"
            value={view}
            onChange={(v) => go(v)}
            options={[
              { value: "batch", label: "Batch", icon: <Users className="h-4 w-4" aria-hidden /> },
              { value: "teacher", label: "Teacher", icon: <UserRound className="h-4 w-4" aria-hidden /> },
              { value: "room", label: "Room", icon: <DoorOpen className="h-4 w-4" aria-hidden /> },
            ]}
          />
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="sm" aria-label={`Previous ${view}`} onClick={() => step(-1)} disabled={options.length < 2} data-testid="entity-prev" icon={<ChevronLeft className="h-4 w-4" aria-hidden />} />
            <select
              className="input !h-9 !w-auto min-w-[11rem] !py-1"
              aria-label={`Choose ${view}`}
              value={entity?.id ?? ""}
              onChange={(e) => go(view, e.target.value)}
              data-testid="entity-picker"
            >
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name} ({o.detail})
                </option>
              ))}
            </select>
            <Button variant="ghost" size="sm" aria-label={`Next ${view}`} onClick={() => step(1)} disabled={options.length < 2} data-testid="entity-next" icon={<ChevronRight className="h-4 w-4" aria-hidden />} />
          </div>

          <div className="flex flex-wrap items-center gap-2 lg:ml-auto">
            <label htmlFor="version-picker" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Version
            </label>
            <select
              id="version-picker"
              className="input !h-9 !w-auto min-w-[13rem] !py-1"
              value={versionId ?? ""}
              onChange={(e) => {
                setSelectedId(null);
                selectVersion(Number(e.target.value));
              }}
              data-testid="version-picker"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label} {"·"} {v.status_label} {"·"} {formatDateTime(v.created_at)}
                </option>
              ))}
            </select>
            <VersionStatusChip version={version} />
            <Button size="sm" icon={<Printer className="h-4 w-4" aria-hidden />} onClick={() => setPrinting(true)} disabled={!entity || printing} data-testid="print-timetable">
              Print
            </Button>
          </div>
        </div>

        <div className="px-3 pb-5 pt-4 lg:px-5">
          {entity ? (
            <>
              <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                <h2 className="text-lg font-semibold text-slate-900" data-testid="entity-title">
                  {entity.name}
                  <span className="ml-2 text-sm font-normal text-slate-500">{entity.detail}</span>
                </h2>
                <p className="text-sm text-slate-500" data-testid="entity-stats">
                  {plural(viewEntries.length, "class", "classes")} {"·"} {plural(periodsPerWeek, "period")} a week
                  {editor.editable && <span className="no-print"> {"·"} drag a class to move it</span>}
                </p>
              </div>
              <TimetableGrid
                days={days}
                periods={periods}
                entries={entries}
                view={view}
                entityId={entity.id}
                colorOf={colorOf}
                unavailable={unavailable}
                conflictEntryIds={conflictIds}
                selectedEntryId={selectedId}
                highlightSlots={editor.highlightSlots}
                highlightEntryIds={editor.highlightEntryIds}
                onEntryClick={(e) => setSelectedId(e.entry_id)}
                {...editor.grid}
              />
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-slate-100 pt-3 text-xs text-slate-600" data-testid="legend">
                {subjectsInView.map(([id, name]) => (
                  <span key={id} className="inline-flex items-center gap-1.5">
                    <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: colorOf(id).accent }} />
                    {name}
                  </span>
                ))}
                <span className="inline-flex items-center gap-1.5">
                  <span className="rounded bg-slate-800 px-1 py-px text-[9px] font-bold uppercase text-white">Lab</span> practical, can span several periods
                </span>
                {view !== "batch" && (
                  <span className="inline-flex items-center gap-1.5">
                    <span className="hatch h-3 w-4 rounded-sm border border-slate-300" /> unavailable
                  </span>
                )}
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-3 w-4 rounded-sm border border-dashed border-slate-300" /> free
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-3 w-4 rounded-sm border-2 border-amber-500" /> needs review
                </span>
              </div>
            </>
          ) : (
            <p className="py-8 text-center text-sm text-slate-500">This dataset has no {view === "batch" ? "batches" : view === "teacher" ? "teachers" : "rooms"}.</p>
          )}
        </div>
      </Card>

      <div className="no-print grid items-start gap-5 lg:grid-cols-2">
        <UnscheduledPanel items={version.unscheduled} view={view} entityId={entity?.id ?? ""} total={summary.total_sessions} renderActions={editor.unscheduledActions} />
        <ConflictsPanel conflicts={validation.conflicts} entries={entries} reviewIds={reviewIds} onSelectEntry={setSelectedId} />
      </div>

      <EntryDrawer
        entry={selected}
        dataset={dataset}
        color={selected ? colorOf(selected.subject_id) : null}
        conflicts={validation.conflicts}
        onClose={() => setSelectedId(null)}
        footer={selected ? editor.drawerFooter(selected) : undefined}
      />
      {editor.dialogs}
      {printing && entity && <PrintSheet version={version} dataset={dataset} view={view} entityIds={[entity.id]} onDone={() => setPrinting(false)} />}
    </>
  );
}
