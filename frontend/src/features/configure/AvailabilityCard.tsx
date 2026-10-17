import { useMemo, useRef, useState } from "react";
import { Ban, Check, DoorOpen, UserRound } from "lucide-react";
import { datasetsApi, errorMessage, type DatasetDetail, type Day } from "../../api";
import { Banner, Card, CardBody, CardHeader, Segmented, useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";
import { breakLabel, dayName, plural, timeRange } from "../../lib/format";
import { ImpactNotice } from "./ImpactNotice";

type Kind = "teacher" | "room";

/** Apply one availability change to a local copy of the dataset (also used to roll back). */
function applyLocal(d: DatasetDetail, id: number, resource: string, day: Day, period: number, available: boolean): DatasetDetail {
  if (d.id !== id) return d; // the user switched dataset while a request was in flight
  const rest = d.availability.filter((r) => !(r.resource_id === resource && r.day === day && r.period === period));
  const availability = available ? rest : [...rest, { resource_id: resource, day, period, available: false as const }];
  return { ...d, availability, counts: { ...d.counts, availability: availability.length } };
}

/** Days x periods grid for one teacher or room. Click a slot to mark it unavailable / available again. */
export function AvailabilityCard({ dataset }: { dataset: DatasetDetail }) {
  const toast = useToast();
  const { patchDatasetLocal, refreshDataset, refreshVersion, refreshVersions } = useApp();
  const [kind, setKind] = useState<Kind>("teacher");
  const [teacherId, setTeacherId] = useState(dataset.teachers[0]?.teacher_id ?? "");
  const [roomId, setRoomId] = useState(dataset.rooms[0]?.room_id ?? "");

  // Requests run one after another so the server sees the clicks in order.
  const queue = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(0);

  const resourceId = kind === "teacher" ? teacherId : roomId;
  const resourceName =
    kind === "teacher"
      ? (dataset.teachers.find((t) => t.teacher_id === teacherId)?.name ?? teacherId)
      : (dataset.rooms.find((r) => r.room_id === roomId)?.name ?? roomId);

  const blocked = useMemo(() => {
    const s = new Set<string>();
    for (const r of dataset.availability) if (r.resource_id === resourceId) s.add(`${r.day}|${r.period}`);
    return s;
  }, [dataset.availability, resourceId]);

  const breaks = dataset.periods.filter((p) => p.is_break).length;

  const toggle = (day: Day, period: number) => {
    const nowAvailable = blocked.has(`${day}|${period}`); // blocked -> make available; free -> make unavailable
    const dsId = dataset.id;
    const resource = resourceId;
    patchDatasetLocal((d) => applyLocal(d, dsId, resource, day, period, nowAvailable));
    pending.current += 1;
    queue.current = queue.current.then(async () => {
      try {
        await datasetsApi.setAvailability(dsId, { resource_id: resource, day, period, available: nowAvailable });
      } catch (err) {
        patchDatasetLocal((d) => applyLocal(d, dsId, resource, day, period, !nowAvailable)); // roll back
        toast.error("Could not save that change", errorMessage(err));
      } finally {
        pending.current -= 1;
        if (pending.current === 0) {
          await refreshDataset(); // sync with the server once every click has been saved
          if (dataset.version_count > 0) {
            void refreshVersions();
            void refreshVersion();
          }
        }
      }
    });
  };

  const noResources = kind === "teacher" ? dataset.teachers.length === 0 : dataset.rooms.length === 0;

  return (
    <Card data-testid="availability-card">
      <CardHeader
        icon={<Ban className="h-5 w-5" aria-hidden />}
        title="Teacher and room availability"
        description="Everyone is available by default. Click a slot to mark it unavailable (for example a meeting or maintenance); click again to undo."
        actions={
          <Segmented<Kind>
            label="Availability for"
            value={kind}
            onChange={setKind}
            options={[
              { value: "teacher", label: "Teachers", icon: <UserRound className="h-4 w-4" aria-hidden /> },
              { value: "room", label: "Rooms", icon: <DoorOpen className="h-4 w-4" aria-hidden /> },
            ]}
          />
        }
      />
      <CardBody className="space-y-4">
        {noResources ? (
          <Banner tone="amber">No {kind === "teacher" ? "teachers" : "rooms"} in this dataset.</Banner>
        ) : (
          <>
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="w-full max-w-xs">
                <label htmlFor="avail-resource" className="label">
                  {kind === "teacher" ? "Teacher" : "Room"}
                </label>
                <select
                  id="avail-resource"
                  className="input"
                  value={resourceId}
                  onChange={(e) => (kind === "teacher" ? setTeacherId(e.target.value) : setRoomId(e.target.value))}
                  data-testid="avail-resource"
                >
                  {kind === "teacher"
                    ? dataset.teachers.map((t) => (
                        <option key={t.teacher_id} value={t.teacher_id}>
                          {t.name} ({t.teacher_id})
                        </option>
                      ))
                    : dataset.rooms.map((r) => (
                        <option key={r.room_id} value={r.room_id}>
                          {r.name} ({r.room_id})
                        </option>
                      ))}
                </select>
              </div>
              <div className="flex items-center gap-4 text-xs text-slate-600">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-4 w-4 rounded border border-emerald-300 bg-emerald-50" /> Available
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="hatch-red h-4 w-4 rounded border border-red-300" /> Unavailable
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="break-band h-4 w-4 rounded border border-slate-200" /> Break
                </span>
              </div>
            </div>

            <p className="text-sm text-slate-600" aria-live="polite" data-testid="avail-summary">
              <strong className="text-slate-900">{resourceName}</strong> is unavailable for{" "}
              <strong className="text-slate-900" data-testid="avail-count">{plural(blocked.size, "slot")}</strong> a week.
            </p>

            <ImpactNotice />

            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[560px] table-fixed border-separate border-spacing-1" data-testid="availability-grid" data-resource={resourceId}>
                <colgroup>
                  <col className="w-28" />
                  {dataset.days.map((d) => (
                    <col key={d} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    <th className="w-28 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">Period</th>
                    {dataset.days.map((d) => (
                      <th key={d} className="pb-1 text-center text-xs font-semibold uppercase tracking-wide text-slate-500" title={dayName(d)}>
                        {d}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dataset.periods.map((p) =>
                    p.is_break ? (
                      <tr key={p.period}>
                        <td className="pr-2 text-xs text-slate-400">{timeRange(p.start, p.end)}</td>
                        <td colSpan={dataset.days.length} className="break-band rounded-md py-1 text-center text-xs font-medium text-slate-500">
                          {breakLabel(p, breaks)}
                        </td>
                      </tr>
                    ) : (
                      <tr key={p.period}>
                        <td className="pr-2">
                          <div className="text-sm font-semibold text-slate-700">Period {p.period}</div>
                          <div className="text-xs text-slate-400">{timeRange(p.start, p.end)}</div>
                        </td>
                        {dataset.days.map((day) => {
                          const off = blocked.has(`${day}|${p.period}`);
                          return (
                            <td key={day} className="p-0">
                              <button
                                onClick={() => toggle(day, p.period)}
                                aria-pressed={off}
                                aria-label={`${resourceName}, ${dayName(day)} period ${p.period}: ${off ? "unavailable. Click to make available" : "available. Click to mark unavailable"}`}
                                data-testid={`avail-cell-${day}-${p.period}`}
                                data-unavailable={off}
                                className={`flex h-11 w-full items-center justify-center rounded-md border text-xs font-semibold transition-colors ${
                                  off
                                    ? "hatch-red border-red-300 text-red-700 hover:border-red-400"
                                    : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:border-emerald-400 hover:bg-emerald-100"
                                }`}
                              >
                                {off ? (
                                  <span className="rounded bg-white/80 px-1.5 py-0.5">Unavailable</span>
                                ) : (
                                  <Check className="h-4 w-4 opacity-60" aria-hidden />
                                )}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>

            {dataset.version_count > 0 && (
              <p className="text-xs text-slate-500">
                Existing timetables are never changed by this. If a class now falls in an unavailable slot, the Timetable page flags it for review.
              </p>
            )}
          </>
        )}
      </CardBody>
    </Card>
  );
}
