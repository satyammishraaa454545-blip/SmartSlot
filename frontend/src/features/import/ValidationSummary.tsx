import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, XCircle } from "lucide-react";
import type { DatasetDetail, FileSummary, ImportIssue } from "../../api";
import { Badge, Banner, Button, Card, CardBody, CardHeader } from "../../components/ui";
import { plural } from "../../lib/format";
import { COUNT_LABELS } from "./csvDocs";

const UPLOAD_KEY = "(upload)";
const PAGE = 50;

const fileKey = (i: ImportIssue) => i.file ?? UPLOAD_KEY;

export function ValidationSummary({ dataset }: { dataset: DatasetDetail }) {
  const report = dataset.import_report;
  const hasErrors = report.error_count > 0;
  const errors = useMemo(() => report.issues.filter((i) => i.severity === "error"), [report]);
  const warnings = useMemo(() => report.issues.filter((i) => i.severity === "warning"), [report]);
  const [fileFilter, setFileFilter] = useState<string | null>(null);
  const [showFiles, setShowFiles] = useState(false);

  // per-file issue counts for the filter chips
  const fileCounts = useMemo(() => {
    const m = new Map<string, { errors: number; warnings: number }>();
    for (const i of report.issues) {
      const k = fileKey(i);
      const c = m.get(k) ?? { errors: 0, warnings: 0 };
      if (i.severity === "error") c.errors++;
      else c.warnings++;
      m.set(k, c);
    }
    return Array.from(m.entries());
  }, [report]);

  const visibleErrors = fileFilter ? errors.filter((i) => fileKey(i) === fileFilter) : errors;
  const visibleWarnings = fileFilter ? warnings.filter((i) => fileKey(i) === fileFilter) : warnings;

  return (
    <section aria-labelledby="validation-title" data-testid="validation-summary" data-status={report.status}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id="validation-title" className="flex items-center gap-2 text-lg font-semibold text-slate-900">
          <ClipboardCheck className="h-5 w-5 text-indigo-600" aria-hidden />
          Validation summary
          <span className="text-sm font-normal text-slate-500">
            {"·"} {dataset.name}
          </span>
        </h2>
      </div>

      {/* entity counts */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-9" data-testid="count-cards">
        {COUNT_LABELS.map(({ key, label }) => (
          <div key={key} className="card px-4 py-3" data-testid={`count-${key}`}>
            <div className="text-2xl font-bold tabular-nums text-slate-900">{dataset.counts[key] ?? 0}</div>
            <div className="mt-0.5 text-xs font-medium text-slate-500">{label}</div>
          </div>
        ))}
        <div className="card border-indigo-200 bg-indigo-50 px-4 py-3" data-testid="count-sessions">
          <div className="text-2xl font-bold tabular-nums text-indigo-700">{dataset.total_sessions}</div>
          <div className="mt-0.5 text-xs font-semibold text-indigo-700">Sessions per week</div>
        </div>
      </div>

      {/* big state */}
      <div className="mt-4">
        {hasErrors ? (
          <Banner tone="red" role="alert" data-testid="blocked-banner" title={`Generation is blocked until these ${plural(report.error_count, "error")} are fixed`}>
            Some rows in your files could not be used. Correct them in your spreadsheet, then import the corrected files again
            (this creates a new dataset; you can delete this one below). Rows that were valid have been kept.
          </Banner>
        ) : (
          <div
            className="flex flex-wrap items-center gap-5 rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white px-6 py-6"
            data-testid="success-state"
          >
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 className="h-8 w-8" aria-hidden />
            </span>
            <div className="min-w-[15rem] flex-1">
              <h3 className="text-xl font-bold text-emerald-900">All files passed validation</h3>
              <p className="mt-0.5 text-sm text-emerald-800/80">
                {plural(dataset.total_sessions, "session")} per week are ready to be scheduled
                {report.warning_count > 0 ? ` (${plural(report.warning_count, "warning")} to look at, shown below).` : ". No problems found."}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Link to="/configure">
                <Button>Review configuration</Button>
              </Link>
              <Link to="/generate">
                <Button variant="success" icon={<ArrowRight className="h-4 w-4" aria-hidden />} data-testid="go-generate">
                  Generate timetable
                </Button>
              </Link>
            </div>
          </div>
        )}
      </div>

      {/* file filter chips */}
      {fileCounts.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-2" role="group" aria-label="Filter by file" data-testid="file-filters">
          <span className="mr-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Filter by file</span>
          <FilterChip active={fileFilter === null} onClick={() => setFileFilter(null)} testId="filter-all">
            All files
            <span className="ml-1.5 rounded-full bg-slate-200 px-1.5 text-[11px] text-slate-700">{report.issues.length}</span>
          </FilterChip>
          {fileCounts.map(([f, c]) => (
            <FilterChip key={f} active={fileFilter === f} onClick={() => setFileFilter(fileFilter === f ? null : f)} testId={`filter-${f}`}>
              {f}
              {c.errors > 0 && <span className="ml-1.5 rounded-full bg-red-100 px-1.5 text-[11px] text-red-700">{c.errors}</span>}
              {c.warnings > 0 && <span className="ml-1 rounded-full bg-amber-100 px-1.5 text-[11px] text-amber-800">{c.warnings}</span>}
            </FilterChip>
          ))}
        </div>
      )}

      {errors.length > 0 && (
        <Card className="mt-3">
          <CardHeader
            icon={<XCircle className="h-5 w-5 text-red-600" aria-hidden />}
            title={fileFilter ? `Errors (${visibleErrors.length} of ${errors.length})` : `Errors (${errors.length})`}
            description="These must be fixed before a timetable can be generated."
            className="!pt-4"
          />
          <CardBody className="!pt-3">
            <IssuesTable issues={visibleErrors} testId="errors-table" />
          </CardBody>
        </Card>
      )}

      {warnings.length > 0 && (
        <Card className="mt-4">
          <CardHeader
            icon={<AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />}
            title={fileFilter ? `Warnings (${visibleWarnings.length} of ${warnings.length})` : `Warnings (${warnings.length})`}
            description="These do not block generation, but are worth a look."
            className="!pt-4"
          />
          <CardBody className="!pt-3">
            <IssuesTable issues={visibleWarnings} testId="warnings-table" />
          </CardBody>
        </Card>
      )}

      {report.truncated && (
        <p className="mt-3 text-xs text-slate-500">
          Only the first issues of each file are listed here. The counts above are exact.
        </p>
      )}

      {/* per-file details */}
      <div className="mt-4">
        <button
          onClick={() => setShowFiles((v) => !v)}
          className="flex items-center gap-1.5 text-sm font-semibold text-slate-600 hover:text-slate-900"
          aria-expanded={showFiles}
          data-testid="toggle-file-details"
        >
          {showFiles ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
          What was read from each file
        </button>
        {showFiles && <FileTable files={report.files} />}
      </div>
    </section>
  );
}

function FilterChip({ active, onClick, children, testId }: { active: boolean; onClick: () => void; children: React.ReactNode; testId: string }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      data-testid={testId}
      className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
        active ? "border-indigo-600 bg-indigo-600 text-white [&_span]:!bg-white/25 [&_span]:!text-white" : "border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:bg-slate-50"
      }`}
    >
      {children}
    </button>
  );
}

function IssuesTable({ issues, testId }: { issues: ImportIssue[]; testId: string }) {
  const [limit, setLimit] = useState(PAGE);
  if (issues.length === 0) return <p className="text-sm text-slate-500">Nothing to show for this file.</p>;
  const shown = issues.slice(0, limit);
  return (
    <div>
      <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full min-w-[820px] border-collapse text-left" data-testid={testId}>
          <thead className="bg-slate-50">
            <tr>
              <th className="th">Severity</th>
              <th className="th">File</th>
              <th className="th text-right">Row</th>
              <th className="th">Field</th>
              <th className="th">Value</th>
              <th className="th">What is wrong</th>
              <th className="th">How to fix it</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {shown.map((i, idx) => (
              <tr key={idx} className="hover:bg-slate-50/60" data-testid="issue-row">
                <td className="td">
                  {i.severity === "error" ? <Badge tone="red" size="sm">Error</Badge> : <Badge tone="amber" size="sm">Warning</Badge>}
                </td>
                <td className="td whitespace-nowrap font-medium text-slate-800">{i.file ?? "Upload"}</td>
                <td className="td text-right tabular-nums">{i.row ?? "-"}</td>
                <td className="td">{i.field ? <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs">{i.field}</code> : "-"}</td>
                <td className="td min-w-[6.5rem] max-w-[11rem]">
                  {i.value ? <code className="break-words rounded bg-slate-100 px-1.5 py-0.5 text-xs [overflow-wrap:anywhere]">{i.value}</code> : <span className="text-slate-400">(empty)</span>}
                </td>
                <td className="td min-w-[14rem] text-slate-800">{i.message}</td>
                <td className="td min-w-[14rem] text-emerald-800">{i.how_to_fix}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {issues.length > limit && (
        <div className="mt-3 text-center">
          <Button size="sm" onClick={() => setLimit((l) => l + PAGE)}>
            Show more ({issues.length - limit} remaining)
          </Button>
        </div>
      )}
    </div>
  );
}

function FileTable({ files }: { files: FileSummary[] }) {
  return (
    <div className="scroll-thin mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white">
      <table className="w-full min-w-[560px] text-left" data-testid="file-table">
        <thead className="bg-slate-50">
          <tr>
            <th className="th">File</th>
            <th className="th">Status</th>
            <th className="th text-right">Rows</th>
            <th className="th text-right">Accepted</th>
            <th className="th text-right">Rejected</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {files.map((f) => (
            <tr key={f.file}>
              <td className="td font-medium text-slate-800">{f.file}</td>
              <td className="td">
                {!f.present ? (
                  f.required ? <Badge tone="red" size="sm">Missing</Badge> : <Badge tone="slate" size="sm">Not provided (optional)</Badge>
                ) : f.errors > 0 ? (
                  <Badge tone="red" size="sm">{plural(f.errors, "error")}</Badge>
                ) : f.warnings > 0 ? (
                  <Badge tone="amber" size="sm">{plural(f.warnings, "warning")}</Badge>
                ) : (
                  <Badge tone="green" size="sm">OK</Badge>
                )}
              </td>
              <td className="td text-right tabular-nums">{f.present ? f.rows : "-"}</td>
              <td className="td text-right tabular-nums">{f.present ? f.accepted : "-"}</td>
              <td className="td text-right tabular-nums">{f.present ? f.rejected : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
