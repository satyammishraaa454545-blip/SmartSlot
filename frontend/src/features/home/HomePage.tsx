import { Link } from "react-router-dom";
import { ArrowRight, CalendarCheck2, FileUp, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { Button, Card } from "../../components/ui";
import { LogoMark } from "../../components/layout/Logo";
import { useApp } from "../../state/AppState";
import { plural } from "../../lib/format";

const STEPS = [
  { icon: FileUp, title: "Import", text: "Upload your teachers, subjects, batches, rooms and weekly requirements as CSV files. Every row is checked, and mistakes are explained." },
  { icon: Wand2, title: "Generate", text: "SmartSlot builds a weekly timetable with no teacher, room or batch clashes, respecting availability and room types." },
  { icon: CalendarCheck2, title: "Review", text: "See the timetable by batch, teacher or room. Anything that could not be placed is listed with the reason." },
  { icon: ShieldCheck, title: "Publish", text: "Fix, validate and publish a verified version. Earlier versions are always kept." },
];

export function HomePage() {
  const { datasets, dataset, version, versions } = useApp();
  const hasData = datasets.length > 0;

  // the next sensible action for someone coming back
  const next = !dataset
    ? null
    : dataset.import_status === "has_errors"
      ? { to: "/import", label: "Fix the import errors", text: `${plural(dataset.error_count, "error")} must be fixed before a timetable can be generated.` }
      : versions.length === 0
        ? { to: "/generate", label: "Generate a timetable", text: `${plural(dataset.total_sessions, "session")} per week are ready to be scheduled.` }
        : { to: "/timetable", label: "Open the timetable", text: version ? `Latest: ${version.label} (${version.status_label}).` : "Review the latest version." };

  return (
    <div className="mx-auto max-w-4xl space-y-8 py-4" data-testid="home">
      <section className="text-center">
        <LogoMark className="mx-auto h-14 w-14" />
        <h1 className="mt-5 text-3xl font-bold text-slate-900 sm:text-4xl">Welcome to SmartSlot</h1>
        <p className="mx-auto mt-3 max-w-2xl text-base leading-relaxed text-slate-600">
          A college timetable that is built, checked and published without anyone having to hunt for clashes. No teacher teaches two classes at once, no room is
          double-booked, and every problem is explained in plain language.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          {hasData && next ? (
            <Link to={next.to}>
              <Button variant="primary" size="lg" icon={<ArrowRight className="h-5 w-5" aria-hidden />} data-testid="home-next">
                {next.label}
              </Button>
            </Link>
          ) : (
            <Link to="/import">
              <Button variant="primary" size="lg" icon={<FileUp className="h-5 w-5" aria-hidden />} data-testid="home-start">
                Start by importing your data
              </Button>
            </Link>
          )}
          {!hasData && (
            <Link to="/import">
              <Button size="lg" icon={<Sparkles className="h-5 w-5" aria-hidden />}>
                Try a demo dataset
              </Button>
            </Link>
          )}
        </div>
        {hasData && next && <p className="mt-3 text-sm text-slate-500">{next.text}</p>}
      </section>

      <section className="grid gap-4 sm:grid-cols-2" aria-label="How it works">
        {STEPS.map((s, i) => (
          <Card key={s.title} className="flex gap-4 p-5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600">
              <s.icon className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                <span className="mr-1.5 text-indigo-500">{i + 1}.</span>
                {s.title}
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-600">{s.text}</p>
            </div>
          </Card>
        ))}
      </section>

      <p className="text-center text-xs text-slate-400">SmartSlot works from CSV files you upload. It does not connect to a live ERP system.</p>
    </div>
  );
}
