import { Link } from "react-router-dom";
import { ChevronDown, Database } from "lucide-react";
import { useApp } from "../../state/AppState";
import { LogoMark } from "./Logo";
import { ValidationBadge, VersionStatusChip } from "../status/StatusBadges";

/** Persistent header: product name, current dataset (switchable), current version + status. */
export function Header() {
  const { datasets, datasetId, selectDataset, dataset, version, versionStatus } = useApp();
  const current = datasets.find((d) => d.id === datasetId) ?? null;

  return (
    <header className="z-20 flex h-16 shrink-0 items-center gap-4 border-b border-slate-200 bg-white px-4 lg:px-6" data-testid="app-header">
      <Link to="/" className="flex shrink-0 items-center gap-2.5" aria-label="SmartSlot home">
        <LogoMark />
        <div className="hidden leading-tight sm:block">
          <div className="text-[17px] font-bold tracking-tight text-slate-900">SmartSlot</div>
          <div className="hidden text-[11px] font-medium text-slate-500 lg:block">College timetable scheduler</div>
        </div>
      </Link>

      <div className="mx-1 hidden h-8 w-px bg-slate-200 sm:block" />

      <div className="min-w-0 flex-1">
        {datasets.length === 0 ? (
          <p className="truncate text-sm text-slate-500" data-testid="header-dataset">
            No dataset yet
          </p>
        ) : (
          <label className="relative block max-w-lg">
            <span className="sr-only">Current dataset</span>
            <Database className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <select
              value={datasetId ?? ""}
              onChange={(e) => selectDataset(Number(e.target.value))}
              className="h-10 w-full cursor-pointer appearance-none truncate rounded-lg border border-slate-200 bg-slate-50 py-1 pl-9 pr-9 text-sm font-medium text-slate-800 hover:border-slate-300 focus:border-indigo-500"
              data-testid="header-dataset"
              title={current ? `${current.name} · Semester ${current.semester}` : undefined}
            >
              {datasets.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} {"·"} Sem {d.semester || "-"}
                </option>
              ))}
            </select>
            <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
          </label>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2" data-testid="header-version">
        {dataset && versionStatus !== "loading" && version ? (
          <>
            <span className="hidden max-w-[10rem] truncate text-sm font-semibold text-slate-700 xl:block" title={version.label}>
              {version.label}
            </span>
            <VersionStatusChip version={version} />
            <ValidationBadge summary={version.summary} />
          </>
        ) : dataset && versionStatus !== "loading" ? (
          <span className="text-sm text-slate-500">No timetable generated yet</span>
        ) : null}
      </div>
    </header>
  );
}
