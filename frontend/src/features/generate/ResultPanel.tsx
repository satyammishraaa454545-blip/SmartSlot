import { AlertTriangle, ArrowRight, CheckCircle2, Clock, Gauge, Lightbulb, RefreshCw, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, Card, CardBody } from "../../components/ui";
import type { LastGeneration } from "../../state/AppState";
import { plural } from "../../lib/format";

const fmtMs = (ms: number) => (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`);

interface Props {
  gen: LastGeneration;
  onOpen: () => void;
  onRetryHigher?: () => void;
}

/** Result of the last "Generate" click, using the exact semantics returned by the API. */
export function ResultPanel({ gen, onOpen, onRetryHigher }: Props) {
  const { result, summary, unscheduled } = gen;
  const s = result.stats;
  const total = s.total_sessions;
  const placed = s.scheduled_count;
  const missing = total - placed;
  const conflicts = summary.error_count;

  // Pick the headline. A search limit is never presented as proof that no timetable exists.
  let tone: "green" | "amber" | "red";
  let title: string;
  let icon: JSX.Element;
  if (result.status === "complete") {
    tone = "green";
    title = `Complete & valid — all ${total} sessions scheduled, ${plural(conflicts, "conflict")}`;
    icon = <CheckCircle2 className="h-8 w-8" aria-hidden />;
  } else if (s.hit_limit) {
    tone = "red";
    title = "No complete solution found within the search limit";
    icon = <XCircle className="h-8 w-8" aria-hidden />;
  } else if (result.status === "partial") {
    tone = "amber";
    title = `Partial — ${placed} of ${total} scheduled, ${missing} could not be placed`;
    icon = <AlertTriangle className="h-8 w-8" aria-hidden />;
  } else {
    tone = "red";
    title = "No timetable could be built from this data";
    icon = <XCircle className="h-8 w-8" aria-hidden />;
  }

  const palette = {
    green: { box: "border-emerald-200 bg-gradient-to-br from-emerald-50 to-white", icon: "bg-emerald-100 text-emerald-600", title: "text-emerald-900", text: "text-emerald-900/80" },
    amber: { box: "border-amber-200 bg-gradient-to-br from-amber-50 to-white", icon: "bg-amber-100 text-amber-600", title: "text-amber-900", text: "text-amber-900/80" },
    red: { box: "border-red-200 bg-gradient-to-br from-red-50 to-white", icon: "bg-red-100 text-red-600", title: "text-red-900", text: "text-red-900/80" },
  }[tone];

  const shown = unscheduled.slice(0, 5);

  return (
    <div className="space-y-4" data-testid="generation-result" data-status={result.status} data-hit-limit={s.hit_limit}>
      <div className={`flex flex-wrap items-center gap-5 rounded-2xl border px-6 py-6 ${palette.box}`} role="status">
        <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-full ${palette.icon}`}>{icon}</span>
        <div className="min-w-0 flex-1">
          <h2 className={`text-xl font-bold ${palette.title}`} data-testid="result-title">
            {title}
          </h2>
          <p className={`mt-1 text-sm ${palette.text}`} data-testid="result-message">
            {result.message}
          </p>
          <p className="mt-1.5 text-sm text-slate-600">
            Saved as a new draft: <strong>{gen.versionLabel}</strong>. Any published timetable has not been changed.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {onRetryHigher && (
            <Button icon={<RefreshCw className="h-4 w-4" aria-hidden />} onClick={onRetryHigher} data-testid="btn-retry-higher">
              Retry with higher limits
            </Button>
          )}
          <Button variant="primary" onClick={onOpen} icon={<ArrowRight className="h-4 w-4" aria-hidden />} data-testid="btn-open-timetable">
            Open timetable
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="result-stats">
        <Stat icon={<CheckCircle2 className="h-4 w-4" aria-hidden />} label="Sessions scheduled" value={`${placed} / ${total}`} />
        <Stat icon={<Gauge className="h-4 w-4" aria-hidden />} label="Search steps" value={s.nodes.toLocaleString()} sub={`limit ${s.max_nodes.toLocaleString()}`} />
        <Stat icon={<Clock className="h-4 w-4" aria-hidden />} label="Time taken" value={fmtMs(s.elapsed_ms)} sub={`limit ${s.time_limit_s}s`} />
        <Stat
          icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
          label="Search limit"
          value={s.hit_limit ? "Reached" : "Not reached"}
          sub={s.hit_limit ? "A solution may still exist" : s.exhausted ? "All arrangements checked" : undefined}
          tone={s.hit_limit ? "amber" : undefined}
        />
      </div>

      {(result.findings.length > 0 || unscheduled.length > 0) && (
        <Card data-testid="unscheduled-summary">
          <CardBody className="space-y-4">
            {result.findings.length > 0 && (
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden /> Why some sessions could not be placed
                </h3>
                <ul className="mt-2 list-disc space-y-1 pl-6 text-sm text-slate-700">
                  {result.findings.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {unscheduled.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-900">
                  {plural(unscheduled.length, "unscheduled session")}
                </h3>
                <ul className="mt-2 divide-y divide-slate-100 rounded-xl border border-dashed border-amber-300 bg-amber-50/40">
                  {shown.map((u) => (
                    <li key={u.session_id} className="px-4 py-3 text-sm" data-testid="unscheduled-item">
                      <div className="font-semibold text-slate-900">
                        {u.subject_name} <span className="font-normal text-slate-500">{"·"} {u.batch_name} {"·"} {u.teacher_name}</span>
                        <span className="ml-2 text-xs font-normal text-slate-500">
                          session {u.index} of {u.of}, {plural(u.duration, "period")}
                        </span>
                      </div>
                      {u.reasons[0] && <p className="mt-0.5 text-slate-700">{u.reasons[0]}</p>}
                      {u.hints[0] && <p className="mt-0.5 text-emerald-800">Tip: {u.hints[0]}</p>}
                    </li>
                  ))}
                </ul>
                {unscheduled.length > shown.length && (
                  <p className="mt-2 text-sm text-slate-500">
                    and {unscheduled.length - shown.length} more.{" "}
                    <Link to="/timetable" className="font-semibold text-indigo-700 hover:underline">
                      See all on the Timetable page
                    </Link>
                  </p>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Stat({ icon, label, value, sub, tone }: { icon: JSX.Element; label: string; value: string; sub?: string; tone?: "amber" }) {
  return (
    <div className={`card px-4 py-3 ${tone === "amber" ? "border-amber-200 bg-amber-50" : ""}`}>
      <div className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-xl font-bold tabular-nums text-slate-900">{value}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}
