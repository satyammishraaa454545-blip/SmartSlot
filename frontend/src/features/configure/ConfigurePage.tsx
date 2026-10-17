import { Link } from "react-router-dom";
import { ArrowRight, TriangleAlert } from "lucide-react";
import { PageHeader } from "../../components/layout/PageHeader";
import { RequireDataset } from "../../components/layout/RequireDataset";
import { Banner, Button } from "../../components/ui";
import type { DatasetDetail } from "../../api";
import { plural } from "../../lib/format";
import { ScheduleConfigCard } from "./ScheduleConfigCard";
import { AvailabilityCard } from "./AvailabilityCard";
import { ResourcesCard } from "./ResourcesCard";
import { RequirementsCard } from "./RequirementsCard";

function SummaryStrip({ dataset }: { dataset: DatasetDetail }) {
  const c = dataset.counts;
  const items: { label: string; value: number | string; strong?: boolean }[] = [
    { label: "Sessions to schedule", value: dataset.total_sessions, strong: true },
    { label: "Teachers", value: c.teachers ?? dataset.teachers.length },
    { label: "Batches", value: c.batches ?? dataset.batches.length },
    { label: "Rooms", value: c.rooms ?? dataset.rooms.length },
    { label: "Days", value: dataset.days.length },
    { label: "Teaching periods / day", value: dataset.teaching_periods.length },
    { label: "Unavailable slots", value: dataset.availability.length },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-7" data-testid="config-summary">
      {items.map((i) => (
        <div key={i.label} className={`card px-4 py-3 ${i.strong ? "border-indigo-200 bg-indigo-50" : ""}`}>
          <div className={`text-2xl font-bold tabular-nums ${i.strong ? "text-indigo-700" : "text-slate-900"}`} data-testid={i.strong ? "total-sessions" : undefined}>
            {i.value}
          </div>
          <div className={`mt-0.5 text-xs font-medium ${i.strong ? "text-indigo-700" : "text-slate-500"}`}>{i.label}</div>
        </div>
      ))}
    </div>
  );
}

export function ConfigurePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        step={2}
        title="Configure"
        description="Check the week the timetable will be built on: working days, period times, who is unavailable when, and room sizes."
        actions={
          <Link to="/generate">
            <Button variant="primary" icon={<ArrowRight className="h-4 w-4" aria-hidden />}>
              Continue to Generate
            </Button>
          </Link>
        }
      />
      <RequireDataset>
        {(dataset) => (
          <>
            <SummaryStrip dataset={dataset} />
            {dataset.import_status === "has_errors" && (
              <Banner tone="amber" icon={<TriangleAlert className="h-5 w-5 text-amber-600" aria-hidden />} title="This dataset had import errors">
                The import found {plural(dataset.error_count, "error")}, so timetables cannot be generated from it. You can still look around, but
                import corrected files to continue.{" "}
                <Link to="/import" className="font-semibold underline">
                  Go to Import
                </Link>
              </Banner>
            )}
            <ScheduleConfigCard key={`cfg-${dataset.id}`} dataset={dataset} />
            <AvailabilityCard key={`av-${dataset.id}`} dataset={dataset} />
            <ResourcesCard dataset={dataset} />
            <RequirementsCard key={`rq-${dataset.id}`} dataset={dataset} />
          </>
        )}
      </RequireDataset>
    </div>
  );
}
