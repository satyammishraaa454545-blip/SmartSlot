import { useEffect, useMemo, useState } from "react";
import { DoorOpen, Download, FileSpreadsheet, FileText, Printer, UserRound, Users } from "lucide-react";
import { errorMessage, exportLinks, versionsApi, type DatasetDetail, type VersionDetail, type VersionMeta, type ViewKind } from "../../api";
import { Button, Card, CardBody, CardHeader, Segmented, useToast } from "../../components/ui";
import { VersionStatusChip } from "../../components/status/StatusBadges";
import { downloadFile, formatBytes } from "../../lib/download";
import { PrintSheet } from "../print/PrintSheet";
import { entityOptions, VIEW_LABEL } from "../timetable/entities";

const VIEWS: ViewKind[] = ["batch", "teacher", "room"];
const ICON: Record<ViewKind, JSX.Element> = {
  batch: <Users className="h-4 w-4" aria-hidden />,
  teacher: <UserRound className="h-4 w-4" aria-hidden />,
  room: <DoorOpen className="h-4 w-4" aria-hidden />,
};

/** CSV and PDF downloads (all pages or a single batch / teacher / room) and a clean print layout. */
export function ExportCard({
  dataset,
  versions,
  preferredId,
  loaded,
}: {
  dataset: DatasetDetail;
  versions: VersionMeta[];
  /** version to preselect (the published one, else the one open in the timetable) */
  preferredId: number | null;
  /** the already loaded full version (saves a request when printing it) */
  loaded: VersionDetail | null;
}) {
  const toast = useToast();
  const [versionId, setVersionId] = useState<number | null>(preferredId);
  const [busy, setBusy] = useState<string | null>(null);
  const [view, setView] = useState<ViewKind>("batch");
  const [entityId, setEntityId] = useState<string>("");
  const [printJob, setPrintJob] = useState<{ version: VersionDetail; view: ViewKind; ids: string[] } | null>(null);

  // follow the preferred version until the user picks one themselves
  const [picked, setPicked] = useState(false);
  useEffect(() => {
    if (!picked) setVersionId(preferredId);
  }, [preferredId, picked]);
  useEffect(() => {
    if (versionId !== null && !versions.some((v) => v.id === versionId)) setVersionId(versions[0]?.id ?? null);
  }, [versions, versionId]);

  const version = versions.find((v) => v.id === versionId) ?? null;
  const options = useMemo(() => entityOptions(dataset, view), [dataset, view]);
  useEffect(() => setEntityId(""), [view]);

  const run = async (key: string, url: string, fallback: string, what: string) => {
    setBusy(key);
    try {
      const f = await downloadFile(url, fallback);
      toast.success(`${what} downloaded`, `${f.fileName} (${formatBytes(f.size)})`, { testId: "toast-downloaded" });
    } catch (err) {
      toast.error(`Could not download the ${what}`, errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const csv = () => version && run("csv", exportLinks.csv(version.id), `smartslot-${version.label}.csv`, "CSV file");
  const pdf = (v: ViewKind, id?: string) =>
    version &&
    run(id ? `pdf-${v}-one` : `pdf-${v}`, exportLinks.pdf(version.id, v, id), `smartslot-${v}-timetable.pdf`, id ? "PDF" : `${VIEW_LABEL[v].one.toLowerCase()} PDF`);

  const print = async () => {
    if (!version) return;
    setBusy("print");
    try {
      const full = loaded && loaded.id === version.id ? loaded : await versionsApi.get(version.id);
      setPrintJob({ version: full, view, ids: entityId ? [entityId] : [] });
    } catch (err) {
      toast.error("Could not prepare the print layout", errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const scheduled = version?.summary.scheduled ?? 0;

  return (
    <Card data-testid="export-card">
      <CardHeader
        icon={<Download className="h-5 w-5" aria-hidden />}
        title="Export and print"
        description="Download the timetable for sharing, or print a clean copy (one batch, teacher or room per page)."
      />
      <CardBody className="space-y-5">
        <div>
          <label htmlFor="export-version" className="label">
            Which version
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <select
              id="export-version"
              className="input min-w-0 flex-1"
              value={versionId ?? ""}
              onChange={(e) => {
                setPicked(true);
                setVersionId(Number(e.target.value));
              }}
              data-testid="export-version"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label} · {v.status_label}
                </option>
              ))}
            </select>
            {version && <VersionStatusChip version={version} size="sm" />}
          </div>
        </div>

        <div>
          <p className="label">Spreadsheet (CSV)</p>
          <Button onClick={() => void csv()} loading={busy === "csv"} disabled={!version || busy !== null} icon={<FileSpreadsheet className="h-4 w-4" aria-hidden />} data-testid="export-csv">
            Download CSV
          </Button>
          <p className="mt-1 text-xs text-slate-500">One row per scheduled class ({scheduled} rows). Opens in Excel.</p>
        </div>

        <div>
          <p className="label">PDF, one page for every...</p>
          <div className="flex flex-wrap gap-2">
            {VIEWS.map((v) => (
              <Button key={v} onClick={() => void pdf(v)} loading={busy === `pdf-${v}`} disabled={!version || busy !== null} icon={ICON[v]} data-testid={`export-pdf-${v}`}>
                {VIEW_LABEL[v].one} PDF
              </Button>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
          <p className="label">Just one timetable, or print</p>
          <div className="flex flex-wrap items-center gap-2">
            <Segmented<ViewKind> label="What to export" value={view} onChange={setView} options={VIEWS.map((v) => ({ value: v, label: VIEW_LABEL[v].one, icon: ICON[v] }))} />
            <select className="input !w-auto min-w-[10rem] flex-1" aria-label={`Choose a ${view}`} value={entityId} onChange={(e) => setEntityId(e.target.value)} data-testid="export-entity">
              <option value="">All {VIEW_LABEL[view].many.toLowerCase()} ({options.length} pages)</option>
              {options.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <Button
              onClick={() => void pdf(view, entityId || undefined)}
              loading={busy === `pdf-${view}-one` || busy === `pdf-${view}`}
              disabled={!version || busy !== null}
              icon={<FileText className="h-4 w-4" aria-hidden />}
              data-testid="export-pdf-entity"
            >
              Download PDF
            </Button>
            <Button onClick={() => void print()} loading={busy === "print"} disabled={!version || busy !== null} icon={<Printer className="h-4 w-4" aria-hidden />} data-testid="print-versions">
              Print
            </Button>
          </div>
        </div>
      </CardBody>
      {printJob && <PrintSheet version={printJob.version} dataset={dataset} view={printJob.view} entityIds={printJob.ids} onDone={() => setPrintJob(null)} />}
    </Card>
  );
}
