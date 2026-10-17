import { useMemo, useState } from "react";
import { CalendarClock, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import {
  ALL_DAYS,
  ApiError,
  DAY_NAMES,
  datasetsApi,
  errorMessage,
  type DatasetDetail,
  type Day,
  type PeriodDef,
} from "../../api";
import { Banner, Button, Card, CardBody, CardHeader, useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";
import { addMinutes, isTime, minutesBetween, plural } from "../../lib/format";

interface Draft {
  days: Day[];
  periods: PeriodDef[];
}

const baseOf = (d: DatasetDetail): Draft => ({ days: d.days, periods: d.periods });
const same = (a: Draft, b: Draft) => JSON.stringify(a) === JSON.stringify(b);

/** Working days chips + editable period table (PUT /datasets/{id}/config). */
export function ScheduleConfigCard({ dataset }: { dataset: DatasetDetail }) {
  const toast = useToast();
  const { applyDatasetDetail, refreshVersion, refreshVersions } = useApp();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [notes, setNotes] = useState<string[]>([]);

  const base = useMemo(() => baseOf(dataset), [dataset]);
  const current = draft ?? base;
  const dirty = draft !== null && !same(draft, base);

  const edit = (fn: (d: Draft) => Draft) => {
    setServerErrors([]);
    setDraft(fn(structuredClone(current)));
  };

  // client-side checks (the server validates again)
  const rowProblems = current.periods.map((p) => {
    if (!isTime(p.start) || !isTime(p.end)) return "Enter a start and end time.";
    if (minutesBetween(p.start, p.end) <= 0) return "End must be later than start.";
    return null;
  });
  const teachingCount = current.periods.filter((p) => !p.is_break).length;
  const problem =
    current.days.length === 0
      ? "Choose at least one working day."
      : teachingCount === 0
        ? "At least one period must be a teaching period (not a break)."
        : (rowProblems.find((p) => p !== null) ?? null);

  const toggleDay = (day: Day) =>
    edit((d) => {
      const has = d.days.includes(day);
      const days = has ? d.days.filter((x) => x !== day) : [...d.days, day];
      return { ...d, days: ALL_DAYS.filter((x) => days.includes(x)) };
    });

  const setPeriod = (idx: number, patch: Partial<PeriodDef>) =>
    edit((d) => ({ ...d, periods: d.periods.map((p, i) => (i === idx ? { ...p, ...patch } : p)) }));

  const addPeriod = () =>
    edit((d) => {
      const last = d.periods[d.periods.length - 1];
      const start = last ? last.end : "09:00";
      return {
        ...d,
        periods: [...d.periods, { period: (last?.period ?? 0) + 1, start, end: addMinutes(start, 50), is_break: false }],
      };
    });

  const removeLast = () => edit((d) => ({ ...d, periods: d.periods.slice(0, -1) }));

  const save = async () => {
    if (!draft || problem) return;
    setSaving(true);
    setServerErrors([]);
    try {
      const res = await datasetsApi.saveConfig(
        dataset.id,
        draft.days,
        draft.periods.map((p) => ({ period: p.period, start: p.start, end: p.end, is_break: p.is_break })),
      );
      applyDatasetDetail(res.dataset);
      setDraft(null);
      setNotes(res.warnings);
      toast.success("Schedule saved", "Working days and periods were updated.");
      if (dataset.version_count > 0) {
        void refreshVersions();
        void refreshVersion();
      }
    } catch (err) {
      if (err instanceof ApiError && err.code === "INVALID_CONFIG" && Array.isArray(err.detail.errors)) {
        setServerErrors((err.detail.errors as { message: string }[]).map((e) => e.message));
      } else {
        toast.error("Could not save the schedule", errorMessage(err));
      }
    } finally {
      setSaving(false);
    }
  };

  const lastIdx = current.periods.length - 1;

  return (
    <Card data-testid="schedule-config">
      <CardHeader
        icon={<CalendarClock className="h-5 w-5" aria-hidden />}
        title="Working days and periods"
        description="Tick the days classes run and set the time of each period. Mark a period as a break to keep it free of classes."
        actions={
          dirty ? (
            <>
              <Button variant="ghost" size="sm" icon={<RotateCcw className="h-4 w-4" aria-hidden />} onClick={() => { setDraft(null); setServerErrors([]); }} disabled={saving}>
                Discard
              </Button>
              <Button variant="primary" size="sm" icon={<Save className="h-4 w-4" aria-hidden />} onClick={() => void save()} loading={saving} disabled={!!problem} data-testid="save-config">
                Save changes
              </Button>
            </>
          ) : undefined
        }
      />
      <CardBody className="space-y-5">
        <div>
          <p className="label">Working days</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Working days">
            {ALL_DAYS.map((day) => {
              const on = current.days.includes(day);
              return (
                <button
                  key={day}
                  onClick={() => toggleDay(day)}
                  aria-pressed={on}
                  title={DAY_NAMES[day]}
                  data-testid={`day-${day}`}
                  className={`h-9 min-w-[3.5rem] rounded-lg border px-3 text-sm font-semibold transition-colors ${
                    on ? "border-indigo-600 bg-indigo-600 text-white shadow-sm" : "border-slate-300 bg-white text-slate-500 hover:border-slate-400 hover:text-slate-700"
                  }`}
                >
                  {day}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="label">Periods</p>
          <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[560px] text-left" data-testid="periods-table">
              <thead className="bg-slate-50">
                <tr>
                  <th className="th w-28">Period</th>
                  <th className="th">Starts</th>
                  <th className="th">Ends</th>
                  <th className="th text-right">Minutes</th>
                  <th className="th">Type</th>
                  <th className="th w-12">
                    <span className="sr-only">Remove</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {current.periods.map((p, idx) => {
                  const bad = rowProblems[idx];
                  return (
                    <tr key={p.period} className={p.is_break ? "bg-slate-50" : ""} data-testid={`period-row-${p.period}`}>
                      <td className="td whitespace-nowrap font-semibold text-slate-900">
                        {p.is_break ? "Break" : `Period ${p.period}`}
                        {p.is_break && <span className="ml-1 text-xs font-normal text-slate-400">(row {p.period})</span>}
                      </td>
                      <td className="td">
                        <input
                          type="time"
                          value={p.start}
                          onChange={(e) => setPeriod(idx, { start: e.target.value })}
                          className={`input !h-9 !w-32 !py-1 ${bad ? "!border-red-400" : ""}`}
                          aria-label={`Period ${p.period} start time`}
                          data-testid={`period-start-${p.period}`}
                        />
                      </td>
                      <td className="td">
                        <input
                          type="time"
                          value={p.end}
                          onChange={(e) => setPeriod(idx, { end: e.target.value })}
                          className={`input !h-9 !w-32 !py-1 ${bad ? "!border-red-400" : ""}`}
                          aria-label={`Period ${p.period} end time`}
                          data-testid={`period-end-${p.period}`}
                        />
                      </td>
                      <td className="td text-right tabular-nums text-slate-500">
                        {bad ? <span className="text-xs text-red-600">{bad}</span> : minutesBetween(p.start, p.end)}
                      </td>
                      <td className="td">
                        <label className="inline-flex cursor-pointer items-center gap-2 whitespace-nowrap text-sm text-slate-700">
                          <input
                            type="checkbox"
                            checked={p.is_break}
                            onChange={(e) => setPeriod(idx, { is_break: e.target.checked })}
                            className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                            data-testid={`period-break-${p.period}`}
                          />
                          {p.is_break ? "Break (no classes)" : "Break"}
                        </label>
                      </td>
                      <td className="td">
                        {idx === lastIdx && current.periods.length > 1 && (
                          <button
                            onClick={removeLast}
                            aria-label={`Remove period ${p.period}`}
                            title="Remove this period"
                            className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <Button size="sm" icon={<Plus className="h-4 w-4" aria-hidden />} onClick={addPeriod} data-testid="add-period">
              Add period
            </Button>
            <p className="text-xs text-slate-500">
              {plural(teachingCount, "teaching period")} a day {"·"} {plural(current.days.length, "day")} a week. Periods are numbered
              in order; only the last one can be removed.
            </p>
          </div>
        </div>

        {problem && dirty && <Banner tone="amber">{problem}</Banner>}
        {serverErrors.length > 0 && (
          <Banner tone="red" role="alert" title="The server did not accept these settings">
            <ul className="list-disc pl-5">
              {serverErrors.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </Banner>
        )}
        {notes.length > 0 && !dirty && (
          <Banner tone="blue" title="Saved. Please note:" data-testid="config-notes" actions={<Button size="sm" variant="ghost" onClick={() => setNotes([])}>Dismiss</Button>}>
            <ul className="list-disc pl-5">
              {notes.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </Banner>
        )}
      </CardBody>
    </Card>
  );
}
