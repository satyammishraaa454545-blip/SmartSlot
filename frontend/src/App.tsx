import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ConfigurePage } from "./features/configure/ConfigurePage";
import { GeneratePage } from "./features/generate/GeneratePage";
import { HomePage } from "./features/home/HomePage";
import { ImportPage } from "./features/import/ImportPage";
import { InsightsPage } from "./features/insights/InsightsPage";
import { TimetablePage } from "./features/timetable/TimetablePage";
import { VersionsPage } from "./features/versions/VersionsPage";

/** Route table: one page per workflow step. */
export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<HomePage />} />
        <Route path="import" element={<ImportPage />} />
        <Route path="configure" element={<ConfigurePage />} />
        <Route path="generate" element={<GeneratePage />} />
        <Route path="timetable" element={<TimetablePage />} />
        <Route path="versions" element={<VersionsPage />} />
        <Route path="insights" element={<InsightsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
