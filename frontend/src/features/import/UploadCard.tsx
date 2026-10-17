import { useRef, useState, type DragEvent } from "react";
import { CheckCircle2, FileSpreadsheet, FileArchive, UploadCloud, X, AlertTriangle, Circle } from "lucide-react";
import { datasetsApi, errorMessage, type ImportResponse } from "../../api";
import { Banner, Button, Card, CardBody, CardHeader, useToast } from "../../components/ui";
import { CSV_FILES, CSV_FILE_NAMES } from "./csvDocs";
import { plural } from "../../lib/format";

interface UploadCardProps {
  onImported: (res: ImportResponse) => void;
  disabled?: boolean;
}

const isZip = (f: File) => f.name.toLowerCase().endsWith(".zip");
const isCsv = (f: File) => f.name.toLowerCase().endsWith(".csv");
const fmtSize = (n: number) => (n < 1024 ? `${n} B` : `${(n / 1024).toFixed(1)} KB`);

export function UploadCard({ onImported, disabled }: UploadCardProps) {
  const toast = useToast();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("");
  const [semester, setSemester] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);

  const addFiles = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    const accepted = list.filter((f) => isCsv(f) || isZip(f));
    const rejected = list.filter((f) => !(isCsv(f) || isZip(f)));
    if (rejected.length > 0) {
      toast.warning(
        "Some files were skipped",
        `${rejected.map((f) => f.name).join(", ")}: only .csv files or one .zip are accepted.`,
      );
    }
    if (accepted.length === 0) return;
    setFiles((cur) => {
      const byName = new Map(cur.map((f) => [f.name.toLowerCase(), f]));
      for (const f of accepted) byName.set(f.name.toLowerCase(), f); // same name replaces the older file
      return Array.from(byName.values());
    });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length > 0) addFiles(e.dataTransfer.files);
  };

  const zips = files.filter(isZip);
  const csvs = files.filter(isCsv);
  const mixed = zips.length > 0 && csvs.length > 0;
  const manyZips = zips.length > 1;
  const present = new Set(csvs.map((f) => f.name.toLowerCase()));
  const requiredMissing = CSV_FILES.filter((f) => f.required && !present.has(f.file));
  const unknown = csvs.filter((f) => !CSV_FILE_NAMES.has(f.name.toLowerCase()));
  const problem = mixed
    ? "Choose either one .zip or separate .csv files, not both. Remove one of them."
    : manyZips
      ? "Please add only one .zip file."
      : null;
  const canSubmit = files.length > 0 && !problem && !busy && !disabled;

  const submit = async () => {
    setBusy(true);
    try {
      const res = await datasetsApi.importFiles(files, name, semester);
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
      onImported(res);
    } catch (err) {
      toast.error("Import failed", errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card data-testid="upload-card">
      <CardHeader
        icon={<UploadCloud className="h-5 w-5" aria-hidden />}
        title="Upload your CSV files"
        description="Drop the 7 required CSV files (plus availability.csv if you have it) or a single .zip."
      />
      <CardBody className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
          <div>
            <label htmlFor="ds-name" className="label">
              Dataset name
            </label>
            <input
              id="ds-name"
              className="input"
              placeholder="e.g. CE Semester 3 - 2026"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
              data-testid="input-dataset-name"
            />
          </div>
          <div>
            <label htmlFor="ds-sem" className="label">
              Semester
            </label>
            <input
              id="ds-sem"
              className="input"
              placeholder="e.g. 3"
              value={semester}
              maxLength={40}
              onChange={(e) => setSemester(e.target.value)}
              data-testid="input-semester"
            />
          </div>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Choose CSV files or drop them here"
          data-testid="dropzone"
          className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors ${
            dragging ? "border-indigo-500 bg-indigo-50" : "border-slate-300 bg-slate-50 hover:border-indigo-400 hover:bg-indigo-50/50"
          }`}
        >
          <UploadCloud className={`h-9 w-9 ${dragging ? "text-indigo-600" : "text-slate-400"}`} aria-hidden />
          <p className="mt-2 text-sm font-semibold text-slate-700">Drag and drop files here, or click to browse</p>
          <p className="mt-0.5 text-xs text-slate-500">.csv files or one .zip, up to 2 MB per file</p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept=".csv,.zip,text/csv,application/zip"
            className="hidden"
            data-testid="file-input"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = ""; // allow picking the same file again
            }}
          />
        </div>

        {/* required-files checklist */}
        <div className="flex flex-wrap gap-1.5" aria-label="Expected files">
          {CSV_FILES.map((f) => {
            const have = present.has(f.file);
            return (
              <span
                key={f.file}
                data-testid={`expect-${f.key}`}
                className={`inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs font-medium ${
                  have
                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                    : "border-slate-200 bg-white text-slate-500"
                }`}
              >
                {have ? (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" aria-hidden />
                ) : (
                  <Circle className="h-3.5 w-3.5 text-slate-300" aria-hidden />
                )}
                {f.file}
                {!f.required && <span className="font-normal text-slate-400">(optional)</span>}
              </span>
            );
          })}
        </div>

        {files.length > 0 && (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200" data-testid="file-list">
            {files.map((f) => {
              const known = isZip(f) || CSV_FILE_NAMES.has(f.name.toLowerCase());
              return (
                <li key={f.name} className="flex items-center gap-3 px-3 py-2 text-sm">
                  {isZip(f) ? (
                    <FileArchive className="h-4 w-4 shrink-0 text-indigo-500" aria-hidden />
                  ) : (
                    <FileSpreadsheet className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                  )}
                  <span className="min-w-0 flex-1 truncate font-medium text-slate-800">{f.name}</span>
                  {!known && (
                    <span className="flex items-center gap-1 text-xs text-amber-700">
                      <AlertTriangle className="h-3.5 w-3.5" aria-hidden /> Unrecognised name, will be ignored
                    </span>
                  )}
                  <span className="shrink-0 text-xs text-slate-400">{fmtSize(f.size)}</span>
                  <button
                    onClick={() => setFiles((cur) => cur.filter((x) => x !== f))}
                    aria-label={`Remove ${f.name}`}
                    className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        {problem && (
          <Banner tone="red" role="alert">
            {problem}
          </Banner>
        )}
        {!problem && files.length > 0 && zips.length === 0 && requiredMissing.length > 0 && (
          <Banner tone="amber">
            Missing {plural(requiredMissing.length, "required file")}: {requiredMissing.map((f) => f.file).join(", ")}. You can still import;
            SmartSlot will list what is missing.
          </Banner>
        )}
        {!problem && unknown.length > 0 && (
          <p className="text-xs text-amber-700">
            {plural(unknown.length, "file")} not named like a template file will be ignored: {unknown.map((f) => f.name).join(", ")}.
          </p>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            {files.length === 0 ? "No files selected yet." : `${plural(files.length, "file")} ready to import.`}
          </p>
          <div className="flex gap-2">
            {files.length > 0 && (
              <Button variant="ghost" onClick={() => setFiles([])} disabled={busy}>
                Clear
              </Button>
            )}
            <Button variant="primary" onClick={submit} disabled={!canSubmit} loading={busy} data-testid="btn-import">
              {busy ? "Importing..." : "Import and validate"}
            </Button>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
