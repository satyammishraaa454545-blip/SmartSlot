import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, Download } from "lucide-react";
import { templateLinks } from "../../api";
import { Badge, Card, CardBody, CardHeader } from "../../components/ui";
import { CSV_FILES } from "./csvDocs";

export function TemplateDocs() {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <Card data-testid="template-docs">
      <CardHeader
        icon={<BookOpen className="h-5 w-5" aria-hidden />}
        title="CSV templates and what each column means"
        description="Download blank templates, fill them in a spreadsheet, and save as CSV (UTF-8)."
        actions={
          <a
            href={templateLinks.zip}
            download
            data-testid="download-templates-zip"
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700"
          >
            <Download className="h-4 w-4" aria-hidden /> All templates (.zip)
          </a>
        }
      />
      <CardBody>
        <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {CSV_FILES.map((f) => {
            const expanded = open === f.file;
            return (
              <li key={f.file} data-testid={`doc-${f.key}`}>
                <div className="flex items-center gap-2 px-3 py-2.5">
                  <button
                    onClick={() => setOpen(expanded ? null : f.file)}
                    aria-expanded={expanded}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    {expanded ? (
                      <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
                    ) : (
                      <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" aria-hidden />
                    )}
                    <span className="font-mono text-sm font-semibold text-slate-900">{f.file}</span>
                    <Badge tone={f.required ? "indigo" : "slate"} size="sm">
                      {f.required ? "Required" : "Optional"}
                    </Badge>
                    <span className="hidden min-w-0 truncate text-sm text-slate-500 md:inline">{f.summary}</span>
                  </button>
                  <a
                    href={templateLinks.file(f.file)}
                    download
                    className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                    aria-label={`Download blank ${f.file}`}
                  >
                    <Download className="h-3.5 w-3.5" aria-hidden /> Template
                  </a>
                </div>
                {expanded && (
                  <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3">
                    <p className="mb-2 text-sm text-slate-600 md:hidden">{f.summary}</p>
                    <table className="w-full text-left">
                      <thead>
                        <tr>
                          <th className="th !px-2">Column</th>
                          <th className="th !px-2">Needed?</th>
                          <th className="th !px-2">What to put there</th>
                        </tr>
                      </thead>
                      <tbody>
                        {f.columns.map((c) => (
                          <tr key={c.name} className="border-t border-slate-100">
                            <td className="td !px-2 font-mono text-xs font-semibold text-slate-800">{c.name}</td>
                            <td className="td !px-2 text-xs">{c.required ? "Yes" : "No"}</td>
                            <td className="td !px-2 text-slate-600">{c.note || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          Tips: the first line of each file is the header. Error messages count rows like a spreadsheet, so the header is row 1 and the
          first data row is row 2. A break such as lunch is its own numbered period with <code className="rounded bg-slate-100 px-1">is_break</code> set
          to 1.
        </p>
      </CardBody>
    </Card>
  );
}
