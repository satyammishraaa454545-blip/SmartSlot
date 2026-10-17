import { useState } from "react";
import { AlertOctagon, CheckCircle2, FlaskConical, Scale } from "lucide-react";
import { datasetsApi, errorMessage, type ImportResponse, type SampleKind } from "../../api";
import { Card, CardBody, CardHeader, Spinner, useToast } from "../../components/ui";

interface DemoOption {
  kind: SampleKind;
  label: string;
  detail: string;
  testId: string;
  icon: JSX.Element;
  tone: string;
}

const OPTIONS: DemoOption[] = [
  {
    kind: "feasible",
    label: "Load demo dataset — complete timetable",
    detail: "6 teachers, 5 subjects, 3 batches, 4 rooms. Every class can be scheduled.",
    testId: "demo-feasible",
    icon: <CheckCircle2 className="h-5 w-5" aria-hidden />,
    tone: "bg-emerald-50 text-emerald-700",
  },
  {
    kind: "infeasible",
    label: "Load demo — impossible requirement",
    detail: "Same college, but the lab is booked more often than it can be. Shows how problems are explained.",
    testId: "demo-infeasible",
    icon: <Scale className="h-5 w-5" aria-hidden />,
    tone: "bg-amber-50 text-amber-700",
  },
  {
    kind: "invalid",
    label: "Load demo — file with errors",
    detail: "CSV files with deliberate mistakes. Shows row-by-row validation and how to fix each one.",
    testId: "demo-invalid",
    icon: <AlertOctagon className="h-5 w-5" aria-hidden />,
    tone: "bg-red-50 text-red-700",
  },
];

export function DemoCard({ onImported, disabled }: { onImported: (res: ImportResponse) => void; disabled?: boolean }) {
  const toast = useToast();
  const [busy, setBusy] = useState<SampleKind | null>(null);

  const load = async (kind: SampleKind) => {
    setBusy(kind);
    try {
      onImported(await datasetsApi.loadSample(kind));
    } catch (err) {
      toast.error("Could not load the demo dataset", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card data-testid="demo-card">
      <CardHeader
        icon={<FlaskConical className="h-5 w-5" aria-hidden />}
        title="Or try a demo dataset"
        description="Sample data bundled with SmartSlot. Nothing leaves your computer."
      />
      <CardBody className="space-y-2.5">
        {OPTIONS.map((o) => (
          <button
            key={o.kind}
            onClick={() => void load(o.kind)}
            disabled={busy !== null || disabled}
            data-testid={o.testId}
            className="flex w-full items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 text-left transition-colors hover:border-indigo-300 hover:bg-indigo-50/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${o.tone}`}>
              {busy === o.kind ? <Spinner className="h-4 w-4" /> : o.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-slate-900">{o.label}</span>
              <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{o.detail}</span>
            </span>
          </button>
        ))}
      </CardBody>
    </Card>
  );
}
