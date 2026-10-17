import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ChevronDown, ChevronRight, CircleCheck, CircleX, FilePlus2, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { ApiError, datasetsApi, errorMessage, type DatasetDetail, type GenerateRequest } from "../../api";
import { PageHeader } from "../../components/layout/PageHeader";
import { RequireDataset } from "../../components/layout/RequireDataset";
import { Banner, Button, Card, CardBody, CardHeader, useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";
import { plural } from "../../lib/format";
import { ResultPanel } from "./ResultPanel";

const DEFAULT_NODES = 200_000;
const DEFAULT_SECONDS = 10;

interface Check {
  ok: boolean;
  label: string;
  detail?: string;
}

function readiness(d: DatasetDetail): { checks: Check[]; blocked: string | null } {
  const checks: Check[] = [
    {
      ok: d.import_status === "ok",
      label: d.import_status === "ok" ? "Import passed validation" : `The import has ${plural(d.error_count, "error")}`,
      detail: d.import_status === "ok" ? undefined : "fix the CSV files and import them again",
    },
    { ok: d.requirements.length > 0, label: "There are classes to schedule", detail: `${d.total_sessions} sessions per week` },
    { ok: d.days.length > 0 && d.teaching_periods.length > 0, label: "Days and teaching periods are set" },
    { ok: d.teachers.length > 0 && d.rooms.length > 0, label: "Teachers and rooms are available" },
  ];
  const first = checks.find((c) => !c.ok);
  return { checks, blocked: first ? `${first.label}${first.detail ? ` — ${first.detail}` : ""}` : null };
}

const PHASES = [
  "Reading your requirements and expanding them into individual sessions...",
  "Searching for an arrangement with no teacher, room or batch clashes...",
  "Checking the result with the independent validator...",
];

export function GeneratePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        step={3}
        title="Generate timetable"
        description="SmartSlot places every session so that no teacher, room or batch is double-booked, then double-checks the result with a separate validator."
      />
      <RequireDataset>{(dataset) => <GenerateBody key={dataset.id} dataset={dataset} />}</RequireDataset>
    </div>
  );
}

function GenerateBody({ dataset }: { dataset: DatasetDetail }) {
  const toast = useToast();
  const navigate = useNavigate();
  const { versions, lastGeneration, setLastGeneration, adoptVersion, refreshDataset, refreshDatasets } = useApp();
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [nodes, setNodes] = useState(String(DEFAULT_NODES));
  const [seconds, setSeconds] = useState(String(DEFAULT_SECONDS));
  const resultRef = useRef<HTMLDivElement>(null);

  const { checks, blocked } = readiness(dataset);
  const published = versions.find((v) => v.status === "published") ?? null;
  const result = lastGeneration && lastGeneration.datasetId === dataset.id ? lastGeneration : null;

  useEffect(() => {
    if (!running) return;
    setElapsed(0);
    const t0 = Date.now();
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 250);
    return () => window.clearInterval(id);
  }, [running]);

  const limitProblem = (() => {
    const n = Number(nodes);
    const s = Number(seconds);
    if (!Number.isInteger(n) || n < 1) return "Maximum search steps must be a whole number of 1 or more.";
    if (!Number.isFinite(s) || s <= 0) return "Maximum time must be more than 0 seconds.";
    return null;
  })();

  const run = async (override?: GenerateRequest) => {
    if (running || blocked) return;
    if (!override && limitProblem) {
      setAdvanced(true);
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const body: GenerateRequest = override ?? { max_nodes: Number(nodes), time_limit_s: Number(seconds) };
      const res = await datasetsApi.generate(dataset.id, body);
      adoptVersion(res.version);
      setLastGeneration({
        datasetId: dataset.id,
        versionId: res.version.id,
        versionLabel: res.version.label,
        result: res.result,
        summary: res.version.summary,
        unscheduled: res.version.unscheduled,
        at: Date.now(),
      });
      void refreshDataset();
      void refreshDatasets();
      window.setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch (err) {
      const msg = errorMessage(err);
      setError(msg);
      toast.error(err instanceof ApiError && err.code === "IMPORT_HAS_ERRORS" ? "Generation is blocked" : "Could not generate the timetable", msg);
    } finally {
      setRunning(false);
    }
  };

  const retryHigher = () => {
    const n = Math.min(Math.max(Number(nodes) * 5, DEFAULT_NODES * 2), 5_000_000);
    const s = Math.min(Math.max(Number(seconds) * 3, DEFAULT_SECONDS * 2), 120);
    setNodes(String(n));
    setSeconds(String(s));
    void run({ max_nodes: n, time_limit_s: s });
  };

  return (
    <>
      <Card className="overflow-hidden" data-testid="generate-card">
        <div className="bg-gradient-to-br from-indigo-50 via-white to-white px-6 py-8 sm:px-10">
          <div className="grid items-center gap-8 lg:grid-cols-[1fr_auto]">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-indigo-700">
                {dataset.name} {"·"} Semester {dataset.semester || "-"}
              </p>
              <h2 className="mt-1 text-2xl font-bold text-slate-900">
                Ready to schedule <span className="text-indigo-700" data-testid="gen-session-count">{plural(dataset.total_sessions, "session")}</span>
              </h2>
              <p className="mt-1 text-sm text-slate-600">
                for {plural(dataset.batches.length, "batch", "batches")} with {plural(dataset.teachers.length, "teacher")} and {plural(dataset.rooms.length, "room")} across{" "}
                {plural(dataset.days.length, "day")}.
              </p>

              <ul className="mt-4 grid gap-1.5 sm:grid-cols-2" aria-label="Readiness checks" data-testid="readiness">
                {checks.map((c) => (
                  <li key={c.label} className="flex items-start gap-2 text-sm">
                    {c.ok ? (
                      <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                    ) : (
                      <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden />
                    )}
                    <span className={c.ok ? "text-slate-700" : "font-medium text-red-700"}>
                      {c.label}
                      {c.detail && <span className="font-normal text-slate-500"> {"—"} {c.detail}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex flex-col items-stretch gap-2 lg:w-72">
              <Button
                variant="primary"
                size="lg"
                onClick={() => void run()}
                disabled={!!blocked || running}
                loading={running}
                icon={!running ? <Sparkles className="h-5 w-5" aria-hidden /> : undefined}
                data-testid="btn-generate"
                className="w-full !h-14 !text-base shadow-md"
              >
                {running ? "Generating..." : "Generate Timetable"}
              </Button>
              {blocked && (
                <p className="text-center text-xs text-red-700" role="alert" data-testid="generate-blocked">
                  Generate is disabled: {blocked}.{" "}
                  <Link to="/import" className="font-semibold underline">
                    Open Import
                  </Link>
                </p>
              )}
            </div>
          </div>
        </div>

        <CardBody className="space-y-4 border-t border-slate-100 !pt-5">
          <div className="flex items-start gap-3 rounded-xl bg-slate-50 p-3.5 text-sm text-slate-700" data-testid="draft-note">
            <FilePlus2 className="mt-0.5 h-5 w-5 shrink-0 text-indigo-600" aria-hidden />
            <p>
              Generating always creates a <strong>new draft</strong>.{" "}
              {published ? (
                <>
                  Your published timetable <strong>{published.label}</strong> is not touched. It stays exactly as it is until you publish a different version.
                </>
              ) : (
                <>Nothing is published until you choose to publish a version, so it is safe to try as often as you like.</>
              )}{" "}
              {versions.length > 0 && <span className="text-slate-500">This dataset has {plural(versions.length, "version")} so far.</span>}
            </p>
          </div>

          <div>
            <button
              onClick={() => setAdvanced((v) => !v)}
              aria-expanded={advanced}
              className="flex items-center gap-1.5 text-sm font-semibold text-slate-600 hover:text-slate-900"
              data-testid="toggle-advanced"
            >
              {advanced ? <ChevronDown className="h-4 w-4" aria-hidden /> : <ChevronRight className="h-4 w-4" aria-hidden />}
              Advanced: search limit
            </button>
            {advanced && (
              <div className="mt-3 rounded-xl border border-slate-200 p-4" data-testid="advanced-panel">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="max-nodes" className="label">
                      Maximum search steps
                    </label>
                    <input id="max-nodes" type="number" min={1} className="input" value={nodes} onChange={(e) => setNodes(e.target.value)} data-testid="input-max-nodes" />
                  </div>
                  <div>
                    <label htmlFor="time-limit" className="label">
                      Maximum time (seconds)
                    </label>
                    <input id="time-limit" type="number" min={1} step={1} className="input" value={seconds} onChange={(e) => setSeconds(e.target.value)} data-testid="input-time-limit" />
                  </div>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-slate-500">
                  SmartSlot tries arrangements one by one. When it reaches either limit it stops and shows the best timetable found so far. Reaching a limit never means the
                  timetable is impossible; try again with higher limits. Defaults: {DEFAULT_NODES.toLocaleString()} steps, {DEFAULT_SECONDS} seconds.
                </p>
                {limitProblem && <p className="mt-2 text-xs font-medium text-red-700">{limitProblem}</p>}
                <Button
                  size="sm"
                  variant="ghost"
                  className="mt-2"
                  onClick={() => {
                    setNodes(String(DEFAULT_NODES));
                    setSeconds(String(DEFAULT_SECONDS));
                  }}
                >
                  Reset to defaults
                </Button>
              </div>
            )}
          </div>
        </CardBody>
      </Card>

      {running && (
        <Card data-testid="generating">
          <div className="flex items-center gap-4 px-6 py-6" role="status" aria-live="polite">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" aria-hidden />
            <div className="min-w-0">
              <p className="font-semibold text-slate-900">Building your timetable...</p>
              <p className="text-sm text-slate-600">{PHASES[Math.min(PHASES.length - 1, Math.floor(elapsed / 2))]}</p>
              <p className="mt-0.5 text-xs text-slate-400">{elapsed}s elapsed. Small datasets usually finish within a second.</p>
            </div>
          </div>
        </Card>
      )}

      {error && !running && (
        <Banner tone="red" role="alert" title="The timetable could not be generated" data-testid="generate-error">
          {error}
        </Banner>
      )}

      <div ref={resultRef} className="scroll-mt-4">
        {result && !running && (
          <ResultPanel
            gen={result}
            onOpen={() => navigate("/timetable")}
            onRetryHigher={result.result.stats.hit_limit ? retryHigher : undefined}
          />
        )}
      </div>

      {!result && !running && !error && (
        <Card>
          <CardHeader icon={<ShieldCheck className="h-5 w-5" aria-hidden />} title="What happens when you click Generate" />
          <CardBody>
            <ol className="space-y-2 text-sm text-slate-600">
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">1</span>
                Each requirement is split into weekly sessions and the hardest ones (fewest possible slots) are placed first.
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">2</span>
                Teacher and room availability, room size and room type are respected. If an arrangement fails, SmartSlot backs up and tries another.
              </li>
              <li className="flex gap-3">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700">3</span>
                A separate validator re-checks the whole timetable. Anything that could not be placed is listed with the reason.
              </li>
            </ol>
            <Link to="/timetable" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-indigo-700 hover:underline">
              {versions.length > 0 ? "View existing timetables" : "Timetable page"} <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          </CardBody>
        </Card>
      )}
    </>
  );
}
