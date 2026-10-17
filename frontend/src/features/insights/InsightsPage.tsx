import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BarChart3, DoorOpen, FlaskConical, GraduationCap, Lightbulb, RefreshCw, Sparkles, Table2, TrendingUp, UserRound, Users } from "lucide-react";
import { errorMessage, isAbort, versionsApi, type Analytics, type VersionMeta } from "../../api";
import { PageHeader } from "../../components/layout/PageHeader";
import { RequireDataset } from "../../components/layout/RequireDataset";
import { VersionStatusChip } from "../../components/status/StatusBadges";
import { Badge, Banner, Button, Card, CardBody, CardHeader, EmptyState, ErrorBoundary, Segmented, Skeleton } from "../../components/ui";
import { formatDateTime, plural } from "../../lib/format";
import { useApp } from "../../state/AppState";
import { average, batchNotes, extremes, roomNotes, teacherNotes, type Note } from "./insights";

export function InsightsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        step={6}
        title="Insights"
        description="How evenly teaching is spread, how busy each room is, and how full each batch's week is. Pick any version to look at."
      />
      <RequireDataset>
        {(dataset) => (
          <ErrorBoundary what="the insights page">
            <InsightsBody key={dataset.id} />
          </ErrorBoundary>
        )}
      </RequireDataset>
    </div>
  );
}

type Mode = "bars" | "table";

function InsightsBody() {
  const { versions, versionId, selectVersion, datasetStatus } = useApp();
  const version = versions.find((v) => v.id === versionId) ?? null;
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("bars");
  const [tick, setTick] = useState(0);

  // re-load when the version changes, or when its content changes (edits change the scheduled counts)
  const fingerprint = version ? `${version.id}:${version.summary.scheduled}:${version.summary.status}` : "";
  useEffect(() => {
    if (versionId === null || !version) {
      setData(null);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    versionsApi
      .analytics(versionId)
      .then((a) => !ctrl.signal.aborted && setData(a))
      .catch((err) => {
        if (isAbort(err) || ctrl.signal.aborted) return;
        setData(null);
        setError(errorMessage(err));
      })
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [versionId, fingerprint, tick]);

  if (datasetStatus === "loading") return <Skeleton className="h-64 w-full" />;

  if (versions.length === 0) {
    return (
      <Card data-testid="insights-empty">
        <EmptyState
          icon={<BarChart3 className="h-7 w-7" aria-hidden />}
          title="Nothing to analyse yet"
          action={
            <Link to="/generate">
              <Button variant="primary" icon={<Sparkles className="h-4 w-4" aria-hidden />}>
                Generate a timetable
              </Button>
            </Link>
          }
        >
          Insights are calculated from a timetable version. Generate one first.
        </EmptyState>
      </Card>
    );
  }

  return (
    <div className="space-y-6" data-testid="insights-page" data-version-id={versionId ?? ""}>
      <div className="card flex flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3">
        <label htmlFor="insights-version" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Version
        </label>
        <select
          id="insights-version"
          className="input !h-9 !w-auto min-w-[16rem] !py-1"
          value={versionId ?? ""}
          onChange={(e) => selectVersion(Number(e.target.value))}
          data-testid="insights-version-picker"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label} · {v.status_label} · {formatDateTime(v.created_at)}
            </option>
          ))}
        </select>
        {version && <VersionStatusChip version={version} />}
        <div className="flex items-center gap-2 sm:ml-auto">
          <Segmented<Mode>
            label="Show as"
            value={mode}
            onChange={setMode}
            options={[
              { value: "bars", label: "Bars", icon: <BarChart3 className="h-4 w-4" aria-hidden /> },
              { value: "table", label: "Table", icon: <Table2 className="h-4 w-4" aria-hidden /> },
            ]}
          />
          <Button variant="ghost" size="sm" aria-label="Refresh" onClick={() => setTick((t) => t + 1)} icon={<RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden />} />
        </div>
      </div>

      {error && (
        <Banner tone="red" role="alert" title="Could not load the insights" actions={<Button onClick={() => setTick((t) => t + 1)}>Try again</Button>}>
          {error}
        </Banner>
      )}
      {!data && !error && (
        <div className="space-y-4" aria-busy="true" data-testid="insights-loading">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-72 w-full" />
        </div>
      )}
      {data && version && <Charts data={data} version={version} mode={mode} stale={loading} />}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
function Charts({ data, version, mode, stale }: { data: Analytics; version: VersionMeta; mode: Mode; stale: boolean }) {
  const t = data.teachers;
  const avgLoad = average(t.map((x) => x.periods_per_week));
  const top = extremes(t, (x) => x.periods_per_week);
  const busiest = [...top.most][0] ?? null;
  const avgRoom = average(data.rooms.map((r) => r.utilization_pct));
  const labs = data.rooms.filter((r) => r.room_type === "lab");
  const avgLab = average(labs.map((r) => r.utilization_pct));
  const days = Array.from(new Set([...t, ...data.rooms, ...data.batches].flatMap((x) => Object.keys(x.per_day))));

  const tNotes = teacherNotes(t);
  const rNotes = roomNotes(data.rooms);
  const bNotes = batchNotes(data.batches);

  return (
    <div className={`space-y-6 transition-opacity ${stale ? "opacity-60" : ""}`}>
      {version.summary.unscheduled > 0 && (
        <Banner tone="amber" data-testid="insights-incomplete" title={`${plural(version.summary.unscheduled, "required session")} not scheduled in this version`}>
          These numbers only count the classes that are on the timetable, so the real load will be higher once everything is placed.
        </Banner>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" data-testid="insights-kpis">
        <Kpi icon={<TrendingUp className="h-4 w-4" aria-hidden />} label="Periods scheduled a week" value={String(data.total_periods_scheduled)} sub={`across ${plural(data.batches.length, "batch", "batches")}`} testId="kpi-periods" />
        <Kpi icon={<UserRound className="h-4 w-4" aria-hidden />} label="Average teacher load" value={`${avgLoad.toFixed(1)}`} sub="periods a week per teacher" testId="kpi-avg-load" />
        <Kpi
          icon={<GraduationCap className="h-4 w-4" aria-hidden />}
          label="Heaviest teaching load"
          value={busiest ? `${top.max}` : t.length ? `${top.max}` : "-"}
          sub={busiest ? `${busiest.name}, periods a week` : "everyone teaches the same"}
          testId="kpi-busiest"
        />
        <Kpi
          icon={<DoorOpen className="h-4 w-4" aria-hidden />}
          label="Average room use"
          value={`${Math.round(avgRoom)}%`}
          sub={labs.length > 0 ? `labs ${Math.round(avgLab)}%` : "of available periods"}
          testId="kpi-room-use"
        />
      </div>

      <Notes notes={[...tNotes.slice(0, 2), ...rNotes.slice(0, 1), ...bNotes.slice(0, 1)]} />

      <Card data-testid="teacher-workload">
        <CardHeader icon={<UserRound className="h-5 w-5" aria-hidden />} title="Teacher workload" description="Periods taught each week (bar) against the periods the teacher is available (grey track). Small columns show Monday to Friday." />
        <CardBody className="space-y-4">
          {mode === "bars" ? (
            <BarList
              testId="teacher-bars"
              rows={[...t]
                .sort((a, b) => b.periods_per_week - a.periods_per_week || a.name.localeCompare(b.name))
                .map((x) => ({
                  id: x.teacher_id,
                  label: x.name,
                  sub: `${x.sessions} sessions`,
                  value: x.periods_per_week,
                  capacity: x.available_periods,
                  valueLabel: `${x.periods_per_week} of ${x.available_periods} periods`,
                  pct: x.utilization_pct,
                  flag: top.most.has(x) ? ("most" as const) : top.least.has(x) ? ("least" as const) : null,
                  perDay: x.per_day,
                }))}
              days={days}
            />
          ) : (
            <DataTable
              testId="teacher-table"
              head={["Teacher", "Sessions", "Periods / week", "Available", "Use", ...days]}
              rows={t.map((x) => [x.name, x.sessions, x.periods_per_week, x.available_periods, `${Math.round(x.utilization_pct)}%`, ...days.map((d) => x.per_day[d] ?? 0)])}
            />
          )}
          <NoteList notes={tNotes} testId="teacher-notes" />
        </CardBody>
      </Card>

      <div className="grid items-start gap-6 xl:grid-cols-2">
        <Card data-testid="room-utilization">
          <CardHeader icon={<DoorOpen className="h-5 w-5" aria-hidden />} title="Room utilisation" description="Share of each room's available periods that are booked. Labs are shown in violet." />
          <CardBody className="space-y-4">
            {mode === "bars" ? (
              <BarList
                testId="room-bars"
                rows={[...data.rooms]
                  .sort((a, b) => b.utilization_pct - a.utilization_pct || a.name.localeCompare(b.name))
                  .map((r) => ({
                    id: r.room_id,
                    label: r.name,
                    sub: r.room_type === "lab" ? "Lab" : "Classroom",
                    value: r.periods_used,
                    capacity: r.available_periods,
                    valueLabel: `${r.periods_used} of ${r.available_periods} periods`,
                    pct: r.utilization_pct,
                    flag: null,
                    lab: r.room_type === "lab",
                    perDay: r.per_day,
                  }))}
                days={days}
                byPercent
              />
            ) : (
              <DataTable
                testId="room-table"
                head={["Room", "Type", "Periods used", "Available", "Use"]}
                rows={data.rooms.map((r) => [r.name, r.room_type, r.periods_used, r.available_periods, `${Math.round(r.utilization_pct)}%`])}
              />
            )}
            <NoteList notes={rNotes} testId="room-notes" />
          </CardBody>
        </Card>

        <Card data-testid="batch-load">
          <CardHeader icon={<Users className="h-5 w-5" aria-hidden />} title="Batch load" description="Periods each batch attends a week, out of all the teaching periods in the week." />
          <CardBody className="space-y-4">
            {mode === "bars" ? (
              <BarList
                testId="batch-bars"
                rows={[...data.batches]
                  .sort((a, b) => b.periods_per_week - a.periods_per_week || a.name.localeCompare(b.name))
                  .map((b) => ({
                    id: b.batch_id,
                    label: b.name,
                    sub: `${b.sessions} sessions`,
                    value: b.periods_per_week,
                    capacity: b.teaching_periods,
                    valueLabel: `${b.periods_per_week} of ${b.teaching_periods} periods`,
                    pct: b.utilization_pct,
                    flag: null,
                    perDay: b.per_day,
                  }))}
                days={days}
              />
            ) : (
              <DataTable
                testId="batch-table"
                head={["Batch", "Sessions", "Periods / week", "Week", "Use"]}
                rows={data.batches.map((b) => [b.name, b.sessions, b.periods_per_week, b.teaching_periods, `${Math.round(b.utilization_pct)}%`])}
              />
            )}
            <NoteList notes={bNotes} testId="batch-notes" />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------------------
function Kpi({ icon, label, value, sub, testId }: { icon: ReactNode; label: string; value: string; sub: string; testId: string }) {
  return (
    <div className="card px-4 py-3.5" data-testid={testId}>
      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-500">
        <span className="text-indigo-600">{icon}</span>
        {label}
      </div>
      <div className="mt-1 text-3xl font-bold tracking-tight text-slate-900">{value}</div>
      <div className="mt-0.5 truncate text-xs text-slate-500" title={sub}>
        {sub}
      </div>
    </div>
  );
}

const NOTE_STYLE: Record<Note["tone"], string> = {
  amber: "border-amber-200 bg-amber-50 text-amber-950",
  blue: "border-sky-200 bg-sky-50 text-sky-950",
  green: "border-emerald-200 bg-emerald-50 text-emerald-950",
  slate: "border-slate-200 bg-slate-50 text-slate-800",
};

function Notes({ notes }: { notes: Note[] }) {
  if (notes.length === 0) return null;
  return (
    <section className="card px-5 py-4" aria-labelledby="stand-out" data-testid="insight-notes">
      <h2 id="stand-out" className="flex items-center gap-2 text-base font-semibold text-slate-900">
        <Lightbulb className="h-5 w-5 text-amber-500" aria-hidden /> What stands out
      </h2>
      <ul className="mt-3 grid gap-2 md:grid-cols-2">
        {notes.map((n, i) => (
          <li key={i} className={`rounded-lg border px-3.5 py-2.5 text-sm ${NOTE_STYLE[n.tone]}`} data-testid="insight-note">
            {n.text}
          </li>
        ))}
      </ul>
    </section>
  );
}

function NoteList({ notes, testId }: { notes: Note[]; testId: string }) {
  if (notes.length === 0) return null;
  return (
    <ul className="space-y-1 border-t border-slate-100 pt-3 text-sm text-slate-700" data-testid={testId}>
      {notes.map((n, i) => (
        <li key={i} className="flex gap-2">
          <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${n.tone === "amber" ? "bg-amber-500" : n.tone === "blue" ? "bg-sky-500" : n.tone === "green" ? "bg-emerald-500" : "bg-slate-400"}`} aria-hidden />
          <span>{n.text}</span>
        </li>
      ))}
    </ul>
  );
}

interface BarRowData {
  id: string;
  label: string;
  sub?: string;
  value: number;
  capacity: number;
  valueLabel: string;
  pct: number;
  flag: "most" | "least" | null;
  lab?: boolean;
  perDay: Record<string, number>;
}

/** Horizontal bars on a common scale: the grey track is the capacity, the coloured bar is what is used. */
function BarList({ rows, days, testId, byPercent }: { rows: BarRowData[]; days: string[]; testId: string; byPercent?: boolean }) {
  const scale = Math.max(1, ...rows.map((r) => r.capacity), ...rows.map((r) => r.value));
  const dayMax = Math.max(1, ...rows.flatMap((r) => Object.values(r.perDay)));
  return (
    <ul className="space-y-3.5" data-testid={testId}>
      {rows.map((r) => {
        const cap = byPercent ? 100 : (r.capacity / scale) * 100;
        const fill = byPercent ? Math.min(100, r.pct) : Math.min(100, (r.value / scale) * 100);
        const color = r.lab ? "bg-violet-500" : r.flag === "most" ? "bg-amber-500" : r.flag === "least" ? "bg-sky-500" : "bg-indigo-500";
        return (
          <li key={r.id} className="grid grid-cols-[minmax(6.5rem,9.5rem)_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5 md:grid-cols-[minmax(7rem,10rem)_minmax(0,1fr)_auto]" data-testid="bar-row" data-id={r.id} data-flag={r.flag ?? undefined} data-value={r.value}>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="truncate text-sm font-semibold text-slate-900">{r.label}</span>
                {r.lab && (
                  <Badge tone="indigo" size="sm" icon={<FlaskConical className="h-3 w-3" aria-hidden />}>
                    Lab
                  </Badge>
                )}
              </div>
              {r.sub && !r.lab && <div className="text-xs text-slate-500">{r.sub}</div>}
              {r.flag && (
                <Badge tone={r.flag === "most" ? "amber" : "blue"} size="sm" className="mt-0.5" data-testid="outlier-tag">
                  {r.flag === "most" ? "Most loaded" : "Lightest load"}
                </Badge>
              )}
            </div>
            <div className="min-w-0">
              <div
                className="relative h-5 rounded-[4px] bg-slate-100"
                style={{ width: `${Math.max(cap, 4)}%` }}
                role="img"
                aria-label={`${r.label}: ${r.valueLabel} (${Math.round(r.pct)}%)`}
              >
                <div className={`absolute inset-y-0 left-0 rounded-r-[4px] ${color}`} style={{ width: `${(fill / Math.max(cap, 4)) * 100}%`, minWidth: r.value > 0 ? "4px" : 0 }} />
              </div>
              <div className="mt-1 text-xs text-slate-600">
                <span className="font-semibold text-slate-800">{r.valueLabel}</span> · {Math.round(r.pct)}%
              </div>
            </div>
            <div className="col-span-2 flex items-center gap-1 md:col-span-1" aria-label={`Periods per day for ${r.label}`}>
              {days.map((d) => {
                const n = r.perDay[d] ?? 0;
                return (
                  <div key={d} className="flex w-5 flex-col items-center gap-px" title={`${d}: ${n} period${n === 1 ? "" : "s"}`}>
                    <span className="text-[10px] font-semibold tabular-nums leading-none text-slate-500">{n}</span>
                    <div className="flex h-5 w-3 items-end rounded-[3px] bg-slate-100">
                      <div className={`w-full rounded-[3px] ${r.lab ? "bg-violet-400" : "bg-indigo-400"}`} style={{ height: `${(n / dayMax) * 100}%`, minHeight: n > 0 ? "2px" : 0 }} />
                    </div>
                    <span className="text-[9px] leading-none text-slate-400">{d.slice(0, 1)}</span>
                  </div>
                );
              })}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function DataTable({ head, rows, testId }: { head: string[]; rows: (string | number)[][]; testId: string }) {
  return (
    <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full min-w-[420px] text-left" data-testid={testId}>
        <thead className="bg-slate-50">
          <tr>
            {head.map((h) => (
              <th key={h} className="th">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((c, j) => (
                <td key={j} className={`td ${j === 0 ? "font-semibold text-slate-900" : "tabular-nums"}`}>
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
