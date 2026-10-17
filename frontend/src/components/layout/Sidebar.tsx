import { NavLink } from "react-router-dom";
import { BarChart3, CalendarDays, FileUp, History, Settings2, Sparkles, type LucideIcon } from "lucide-react";
import { useApp } from "../../state/AppState";

interface NavItem {
  to: string;
  label: string;
  hint: string;
  icon: LucideIcon;
  testId: string;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/import", label: "Import", hint: "Upload your CSV data", icon: FileUp, testId: "nav-import" },
  { to: "/configure", label: "Configure", hint: "Days, periods, availability", icon: Settings2, testId: "nav-configure" },
  { to: "/generate", label: "Generate", hint: "Build the timetable", icon: Sparkles, testId: "nav-generate" },
  { to: "/timetable", label: "Timetable", hint: "Review the weekly grid", icon: CalendarDays, testId: "nav-timetable" },
  { to: "/versions", label: "Publish & Versions", hint: "Publish, compare, export", icon: History, testId: "nav-versions" },
  { to: "/insights", label: "Insights", hint: "Workload and room usage", icon: BarChart3, testId: "nav-insights" },
];

/** Left navigation (icons only on tablet widths, full labels on laptops). */
export function Sidebar() {
  const { dataset, versions } = useApp();

  const status = (to: string): "ok" | "error" | "none" => {
    if (to === "/import" && dataset) return dataset.import_status === "ok" ? "ok" : "error";
    if (to === "/generate" && versions.length > 0) return "ok";
    return "none";
  };

  return (
    <aside className="no-print flex w-[68px] shrink-0 flex-col border-r border-slate-200 bg-white lg:w-64" data-testid="sidebar">
      <nav className="flex-1 space-y-1 p-2.5 lg:p-3" aria-label="Main">
        <p className="hidden px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400 lg:block">Workflow</p>
        {NAV_ITEMS.map((item, i) => {
          const st = status(item.to);
          return (
            <NavLink
              key={item.to}
              to={item.to}
              data-testid={item.testId}
              title={item.label}
              className={({ isActive }) =>
                `group relative flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors max-lg:justify-center ${
                  isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <span
                    className={`relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                      isActive ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500 group-hover:bg-white"
                    }`}
                  >
                    <item.icon className="h-4 w-4" aria-hidden />
                    {st !== "none" && (
                      <span
                        className={`absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-white ${
                          st === "ok" ? "bg-emerald-500" : "bg-red-500"
                        }`}
                        aria-label={st === "ok" ? "Done" : "Needs attention"}
                      />
                    )}
                  </span>
                  <span className="hidden min-w-0 lg:block">
                    <span className="block truncate text-sm font-semibold leading-tight">
                      <span className="mr-1.5 text-xs font-medium opacity-50">{i + 1}</span>
                      {item.label}
                    </span>
                    <span className={`block truncate text-xs leading-tight ${isActive ? "text-indigo-600/80" : "text-slate-400"}`}>
                      {item.hint}
                    </span>
                  </span>
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
      <div className="hidden border-t border-slate-100 p-4 text-xs leading-relaxed text-slate-400 lg:block">
        Works from CSV files you upload. No live ERP connection.
      </div>
    </aside>
  );
}
