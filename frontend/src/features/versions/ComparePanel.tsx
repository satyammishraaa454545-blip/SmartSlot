import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { ArrowLeftRight, ArrowRight, Columns2, DoorOpen, MoveRight, Plus, UserRound, Minus, Equal } from "lucide-react";
import { errorMessage, versionsApi, type Change, type CompareResult, type VersionMeta } from "../../api";
import { Badge, Banner, Button, Card, CardBody, CardHeader, Skeleton } from "../../components/ui";
import type { Tone } from "../../components/ui";
import { VersionStatusChip } from "../../components/status/StatusBadges";
import { plural } from "../../lib/format";

const TYPE_META: Record<Change["type"], { label: string; tone: Tone; bar: string; icon: JSX.Element }> = {
  moved: { label: "Moved", tone: "blue", bar: "border-l-sky-500", icon: <MoveRight className="h-3.5 w-3.5" aria-hidden /> },
  room_changed: { label: "Room changed", tone: "amber", bar: "border-l-amber-500", icon: <DoorOpen className="h-3.5 w-3.5" aria-hidden /> },
  teacher_changed: { label: "Teacher changed", tone: "indigo", bar: "border-l-indigo-500", icon: <UserRound className="h-3.5 w-3.5" aria-hidden /> },
  changed: { label: "Several changes", tone: "indigo", bar: "border-l-violet-500", icon: <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden /> },
  added: { label: "Added", tone: "green", bar: "border-l-emerald-500", icon: <Plus className="h-3.5 w-3.5" aria-hidden /> },
  removed: { label: "Removed", tone: "red", bar: "border-l-red-500", icon: <Minus className="h-3.5 w-3.5" aria-hidden /> },
};

const optionLabel = (v: VersionMeta) => `${v.label} · ${v.status_label}`;

export interface CompareHandle {
  /** compare `from` -> `to` and bring the panel into view */
  run: (from: number, to: number) => void;
}

/** Diff of two versions: counts, colour-coded changes in plain English, affected batches and teachers. */
export const ComparePanel = forwardRef<CompareHandle, { versions: VersionMeta[] }>(function ComparePanel({ versions }, ref) {
  const published = versions.find((v) => v.status === "published") ?? null;
  const newestDraft = versions.find((v) => v.status === "draft") ?? null;

  /** default: the published version against the current draft */
  const defaults = useMemo((): [number | null, number | null] => {
    if (published && newestDraft) return [published.id, newestDraft.id];
    if (versions.length >= 2) return [versions[1].id, versions[0].id];
    return [null, null];
  }, [published, newestDraft, versions]);

  const [from, setFrom] = useState<number | null>(defaults[0]);
  const [to, setTo] = useState<number | null>(defaults[1]);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Change["type"] | "all">("all");
  const ranOnce = useRef(false);
  const seq = useRef(0);
  const root = useRef<HTMLDivElement>(null);

  const exec = useCallback(async (a: number, b: number) => {
    const mine = ++seq.current;
    setLoading(true);
    setError(null);
    setFilter("all");
    try {
      const r = await versionsApi.compare(a, b);
      if (mine === seq.current) setResult(r);
    } catch (err) {
      if (mine === seq.current) {
        setResult(null);
        setError(errorMessage(err));
      }
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      run: (a, b) => {
        setFrom(a);
        setTo(b);
        void exec(a, b);
        window.setTimeout(() => root.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
      },
    }),
    [exec],
  );

  // keep the selections valid when versions come and go, and run the default comparison once
  useEffect(() => {
    const ids = new Set(versions.map((v) => v.id));
    setFrom((cur) => (cur !== null && ids.has(cur) ? cur : defaults[0]));
    setTo((cur) => (cur !== null && ids.has(cur) ? cur : defaults[1]));
  }, [versions, defaults]);
  useEffect(() => {
    if (ranOnce.current || defaults[0] === null || defaults[1] === null) return;
    ranOnce.current = true;
    void exec(defaults[0], defaults[1]);
  }, [defaults, exec]);

  const fromV = versions.find((v) => v.id === from) ?? null;
  const toV = versions.find((v) => v.id === to) ?? null;
  const same = from !== null && from === to;

  const batches = useMemo(() => collect(result?.changes ?? [], (e) => e.batch_name), [result]);
  const teachers = useMemo(() => collect(result?.changes ?? [], (e) => e.teacher_name), [result]);
  const shown = result ? result.changes.filter((c) => filter === "all" || c.type === filter || c.aspects.includes(filter as never)) : [];

  return (
    <div ref={root} className="scroll-mt-4">
      <Card data-testid="compare-card">
        <CardHeader
          icon={<Columns2 className="h-5 w-5" aria-hidden />}
          title="Compare two versions"
          description="See exactly which classes moved, changed room or teacher, or were added or removed. By default this compares the published version with your latest draft."
        />
        <CardBody className="space-y-4">
          {versions.length < 2 ? (
            <Banner tone="blue" data-testid="compare-need-two">
              Comparing needs two versions. Generate again, or restore a version as a draft and edit it, then come back here.
            </Banner>
          ) : (
            <>
              <div className="flex flex-wrap items-end gap-3">
                <div className="min-w-[12rem] flex-1">
                  <label htmlFor="cmp-from" className="label">
                    From (before)
                  </label>
                  <select id="cmp-from" className="input" value={from ?? ""} onChange={(e) => setFrom(Number(e.target.value))} data-testid="compare-from">
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {optionLabel(v)}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  variant="ghost"
                  aria-label="Swap the two versions"
                  onClick={() => {
                    setFrom(to);
                    setTo(from);
                  }}
                  icon={<ArrowLeftRight className="h-4 w-4" aria-hidden />}
                  data-testid="compare-swap"
                />
                <div className="min-w-[12rem] flex-1">
                  <label htmlFor="cmp-to" className="label">
                    To (after)
                  </label>
                  <select id="cmp-to" className="input" value={to ?? ""} onChange={(e) => setTo(Number(e.target.value))} data-testid="compare-to">
                    {versions.map((v) => (
                      <option key={v.id} value={v.id}>
                        {optionLabel(v)}
                      </option>
                    ))}
                  </select>
                </div>
                <Button
                  variant="primary"
                  onClick={() => from !== null && to !== null && void exec(from, to)}
                  disabled={from === null || to === null || same}
                  loading={loading}
                  icon={<Columns2 className="h-4 w-4" aria-hidden />}
                  data-testid="compare-run"
                >
                  Compare
                </Button>
              </div>
              {same && <p className="text-sm text-amber-800">Pick two different versions to compare.</p>}

              {error && (
                <Banner tone="red" role="alert" title="Could not compare these versions">
                  {error}
                </Banner>
              )}
              {loading && !result && (
                <div className="space-y-2" aria-busy="true">
                  <Skeleton className="h-16 w-full" />
                  <Skeleton className="h-12 w-full" />
                </div>
              )}

              {result && (
                <div className={`space-y-4 ${loading ? "opacity-60" : ""}`} data-testid="compare-result" data-changed={result.summary.changed_total}>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
                    <strong className="text-slate-900">{result.from_version.label}</strong>
                    {fromV && <VersionStatusChip version={fromV} size="sm" />}
                    <ArrowRight className="h-4 w-4 text-slate-400" aria-hidden />
                    <strong className="text-slate-900">{result.to_version.label}</strong>
                    {toV && <VersionStatusChip version={toV} size="sm" />}
                  </div>

                  {result.summary.changed_total === 0 ? (
                    <Banner tone="green" data-testid="compare-identical" icon={<Equal className="h-5 w-5 text-emerald-600" aria-hidden />} title="No differences">
                      These two versions have identical timetables ({result.summary.unchanged} classes, all in the same place).
                    </Banner>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" data-testid="compare-summary">
                        {(["moved", "room_changed", "teacher_changed", "added", "removed"] as const).map((t) => {
                          const n = result.summary[t];
                          const meta = TYPE_META[t];
                          const active = filter === t;
                          return (
                            <button
                              key={t}
                              type="button"
                              onClick={() => setFilter(active ? "all" : t)}
                              disabled={n === 0}
                              aria-pressed={active}
                              data-testid={`compare-count-${t}`}
                              data-count={n}
                              className={`rounded-xl border px-3 py-2 text-left transition-colors disabled:opacity-50 ${active ? "ring-2 ring-indigo-500" : ""} ${
                                n > 0 ? "hover:brightness-95" : ""
                              } ${tonedSoft(meta.tone)}`}
                            >
                              <div className="text-xl font-bold tabular-nums">{n}</div>
                              <div className="text-xs font-semibold">{meta.label}</div>
                            </button>
                          );
                        })}
                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700" data-testid="compare-count-unchanged" data-count={result.summary.unchanged}>
                          <div className="text-xl font-bold tabular-nums">{result.summary.unchanged}</div>
                          <div className="text-xs font-semibold">Unchanged</div>
                        </div>
                      </div>

                      <div className="grid gap-3 text-sm sm:grid-cols-2" data-testid="compare-affected">
                        <AffectedChips label="Affected batches" items={batches} />
                        <AffectedChips label="Affected teachers" items={teachers} />
                      </div>

                      <ul className="space-y-2" data-testid="compare-changes">
                        {shown.map((c) => {
                          const meta = TYPE_META[c.type];
                          return (
                            <li
                              key={c.session_id}
                              className={`rounded-lg border border-l-4 border-slate-200 bg-white px-3.5 py-2.5 ${meta.bar}`}
                              data-testid="compare-change"
                              data-type={c.type}
                              data-session-id={c.session_id}
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge tone={meta.tone} size="sm" icon={meta.icon}>
                                  {meta.label}
                                </Badge>
                                <span className="text-sm font-medium text-slate-900">{c.text}</span>
                              </div>
                              <ChangeDetail change={c} />
                            </li>
                          );
                        })}
                      </ul>
                      <p className="text-xs text-slate-500">
                        {plural(result.summary.changed_total, "class", "classes")} changed, {result.summary.unchanged} unchanged. Click a count above to filter.
                      </p>
                    </>
                  )}
                </div>
              )}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
});

function tonedSoft(tone: Tone): string {
  switch (tone) {
    case "blue":
      return "border-sky-200 bg-sky-50 text-sky-900";
    case "amber":
      return "border-amber-200 bg-amber-50 text-amber-900";
    case "indigo":
      return "border-indigo-200 bg-indigo-50 text-indigo-900";
    case "green":
      return "border-emerald-200 bg-emerald-50 text-emerald-900";
    case "red":
      return "border-red-200 bg-red-50 text-red-900";
    default:
      return "border-slate-200 bg-slate-50 text-slate-800";
  }
}

function collect(changes: Change[], pick: (e: NonNullable<Change["before"]>) => string): string[] {
  const set = new Set<string>();
  for (const c of changes) {
    if (c.before) set.add(pick(c.before));
    if (c.after) set.add(pick(c.after));
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

function AffectedChips({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.length === 0 ? (
          <span className="text-slate-400">none</span>
        ) : (
          items.map((i) => (
            <span key={i} className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-700">
              {i}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

const when = (e: NonNullable<Change["before"]>) => `${e.day} P${e.start_period}${e.end_period !== e.start_period ? `–${e.end_period}` : ""}`;

/** Before / after details for the aspects that changed (the headline text already says it in a sentence). */
function ChangeDetail({ change: c }: { change: Change }) {
  const rows: string[] = [];
  if (c.before && c.after) {
    if (c.aspects.includes("moved")) rows.push(`Time: ${when(c.before)} → ${when(c.after)}`);
    if (c.aspects.includes("room_changed")) rows.push(`Room: ${c.before.room_name} → ${c.after.room_name}`);
    if (c.aspects.includes("teacher_changed")) rows.push(`Teacher: ${c.before.teacher_name} → ${c.after.teacher_name}`);
  } else if (c.after) {
    rows.push(`${when(c.after)} · ${c.after.room_name} · ${c.after.teacher_name}`);
  } else if (c.before) {
    rows.push(`Was ${when(c.before)} · ${c.before.room_name} · ${c.before.teacher_name}`);
  }
  if (rows.length === 0) return null;
  return (
    <ul className="mt-1 space-y-0.5 text-xs text-slate-600">
      {rows.map((r) => (
        <li key={r}>{r}</li>
      ))}
    </ul>
  );
}
