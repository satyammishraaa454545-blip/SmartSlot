import { useMemo, useState } from "react";
import { ListChecks } from "lucide-react";
import type { DatasetDetail } from "../../api";
import { Badge, Card, CardBody, CardHeader } from "../../components/ui";
import { plural } from "../../lib/format";

/** Read-only overview of what must be scheduled each week. */
export function RequirementsCard({ dataset }: { dataset: DatasetDetail }) {
  const [batchFilter, setBatchFilter] = useState("");

  const subjects = useMemo(() => new Map(dataset.subjects.map((s) => [s.subject_id, s])), [dataset.subjects]);
  const teachers = useMemo(() => new Map(dataset.teachers.map((t) => [t.teacher_id, t])), [dataset.teachers]);
  const batches = useMemo(() => new Map(dataset.batches.map((b) => [b.batch_id, b])), [dataset.batches]);

  const rows = dataset.requirements.filter((r) => !batchFilter || r.batch_id === batchFilter);
  const sessions = rows.reduce((n, r) => n + r.sessions_per_week, 0);
  const periodsNeeded = rows.reduce((n, r) => n + r.sessions_per_week * r.duration, 0);
  const gridSlots = dataset.days.length * dataset.teaching_periods.length; // teaching periods one batch could use in a week

  return (
    <Card data-testid="requirements-card">
      <CardHeader
        icon={<ListChecks className="h-5 w-5" aria-hidden />}
        title="Requirements overview"
        description="What has to be taught every week. This comes from requirements.csv and is read-only here."
        actions={
          <select
            value={batchFilter}
            onChange={(e) => setBatchFilter(e.target.value)}
            aria-label="Show requirements for"
            className="input !h-9 !w-44 !py-1"
            data-testid="req-batch-filter"
          >
            <option value="">All batches</option>
            {dataset.batches.map((b) => (
              <option key={b.batch_id} value={b.batch_id}>
                {b.name}
              </option>
            ))}
          </select>
        }
      />
      <CardBody>
        <div className="scroll-thin max-h-[26rem] overflow-auto rounded-xl border border-slate-200">
          <table className="w-full min-w-[640px] text-left" data-testid="requirements-table">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                <th className="th">Subject</th>
                <th className="th">Batch</th>
                <th className="th">Teacher</th>
                <th className="th text-right">Sessions / week</th>
                <th className="th text-right">Duration</th>
                <th className="th">Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => {
                const s = subjects.get(r.subject_id);
                const practical = s?.session_type === "practical";
                return (
                  <tr key={`${r.subject_id}|${r.batch_id}|${r.teacher_id}`} data-testid="req-row">
                    <td className="td">
                      <span className="font-medium text-slate-900">{s?.name ?? r.subject_id}</span>{" "}
                      <span className="text-xs text-slate-400">{r.subject_id}</span>
                    </td>
                    <td className="td">{batches.get(r.batch_id)?.name ?? r.batch_id}</td>
                    <td className="td">{teachers.get(r.teacher_id)?.name ?? r.teacher_id}</td>
                    <td className="td text-right tabular-nums">{r.sessions_per_week}</td>
                    <td className="td text-right tabular-nums">{plural(r.duration, "period")}</td>
                    <td className="td">
                      <Badge tone={practical ? "indigo" : "slate"} size="sm">
                        {practical ? "Practical (lab)" : "Lecture"}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="td py-8 text-center text-slate-500">
                    No requirements for this selection.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-sm text-slate-600" data-testid="req-footer">
          <strong className="text-slate-900">{plural(sessions, "session")}</strong> a week, using{" "}
          <strong className="text-slate-900">{plural(periodsNeeded, "period")}</strong>
          {batchFilter && gridSlots > 0 ? ` of the ${gridSlots} teaching periods this batch has each week.` : "."}
        </p>
      </CardBody>
    </Card>
  );
}
