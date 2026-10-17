import { DoorOpen, Users } from "lucide-react";
import { datasetsApi, errorMessage, type Batch, type DatasetDetail, type Room, type RoomType } from "../../api";
import { Badge, Card, CardBody, CardHeader, useToast } from "../../components/ui";
import { useApp } from "../../state/AppState";
import { InlineEdit } from "./InlineEdit";

const positiveInt = (raw: string): string | null => {
  const n = Number(raw);
  return Number.isInteger(n) && n >= 1 && n <= 10000 ? null : "Enter a whole number between 1 and 10000.";
};

/** Rooms and batches with inline editing. Edits are shown immediately and rolled back if the server refuses them. */
export function ResourcesCard({ dataset }: { dataset: DatasetDetail }) {
  const toast = useToast();
  const { patchDatasetLocal, applyDatasetDetail, refreshVersions, refreshVersion } = useApp();
  // existing timetables are re-checked live against the new room data, so the header badge stays truthful
  const resync = (d: DatasetDetail) => {
    if (d.version_count > 0) {
      void refreshVersions();
      void refreshVersion();
    }
  };

  const editRoom = async (room: Room, patch: Partial<Pick<Room, "name" | "capacity" | "room_type">>) => {
    const dsId = dataset.id;
    patchDatasetLocal((d) => (d.id !== dsId ? d : { ...d, rooms: d.rooms.map((r) => (r.room_id === room.room_id ? { ...r, ...patch } : r)) }));
    try {
      const res = await datasetsApi.patchRoom(dsId, room.room_id, patch);
      applyDatasetDetail(res.dataset);
      resync(res.dataset);
      if (res.warnings.length > 0) toast.info("Saved", res.warnings.join(" "));
    } catch (err) {
      patchDatasetLocal((d) => (d.id !== dsId ? d : { ...d, rooms: d.rooms.map((r) => (r.room_id === room.room_id ? room : r)) }));
      toast.error(`Could not update ${room.name}`, errorMessage(err));
    }
  };

  const editBatch = async (batch: Batch, patch: Partial<Pick<Batch, "student_count" | "name">>) => {
    const dsId = dataset.id;
    patchDatasetLocal((d) => (d.id !== dsId ? d : { ...d, batches: d.batches.map((b) => (b.batch_id === batch.batch_id ? { ...b, ...patch } : b)) }));
    try {
      const res = await datasetsApi.patchBatch(dsId, batch.batch_id, patch);
      applyDatasetDetail(res.dataset);
      resync(res.dataset);
    } catch (err) {
      patchDatasetLocal((d) => (d.id !== dsId ? d : { ...d, batches: d.batches.map((b) => (b.batch_id === batch.batch_id ? batch : b)) }));
      toast.error(`Could not update ${batch.name}`, errorMessage(err));
    }
  };

  const invalid = (m: string) => toast.warning("That value was not accepted", m);

  return (
    <div className="grid gap-6 xl:grid-cols-[3fr_2fr]">
      <Card data-testid="rooms-card">
        <CardHeader
          icon={<DoorOpen className="h-5 w-5" aria-hidden />}
          title="Rooms"
          description="Click a name or seat count to change it. Labs only host practicals; classrooms only host lectures."
        />
        <CardBody>
          <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[520px] text-left" data-testid="rooms-table">
              <thead className="bg-slate-50">
                <tr>
                  <th className="th">Room</th>
                  <th className="th">Type</th>
                  <th className="th w-28 text-right">Seats</th>
                  <th className="th">Fits batches</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dataset.rooms.map((r) => {
                  const fits = dataset.batches.filter((b) => b.student_count <= r.capacity);
                  return (
                    <tr key={r.room_id} data-testid={`room-row-${r.room_id}`}>
                      <td className="td !py-1.5">
                        <InlineEdit
                          value={r.name}
                          ariaLabel={`Name of room ${r.room_id}`}
                          onInvalid={invalid}
                          onCommit={(v) => void editRoom(r, { name: v })}
                        />
                        <div className="px-2 text-[11px] text-slate-400">{r.room_id}</div>
                      </td>
                      <td className="td !py-1.5">
                        <select
                          value={r.room_type}
                          onChange={(e) => void editRoom(r, { room_type: e.target.value as RoomType })}
                          aria-label={`Type of ${r.name}`}
                          data-testid={`room-type-${r.room_id}`}
                          className="h-8 rounded-md border border-slate-200 bg-white px-2 text-sm text-slate-700 hover:border-slate-300 focus:border-indigo-500"
                        >
                          <option value="classroom">Classroom</option>
                          <option value="lab">Lab</option>
                        </select>
                      </td>
                      <td className="td !py-1.5">
                        <InlineEdit
                          type="number"
                          min={1}
                          max={10000}
                          align="right"
                          value={r.capacity}
                          ariaLabel={`Seats in ${r.name}`}
                          testId={`room-capacity-${r.room_id}`}
                          validate={positiveInt}
                          onInvalid={invalid}
                          onCommit={(v) => void editRoom(r, { capacity: Number(v) })}
                        />
                      </td>
                      <td className="td !py-1.5">
                        <div className="flex flex-wrap gap-1">
                          {fits.length === 0 ? (
                            <Badge tone="red" size="sm">No batch fits</Badge>
                          ) : (
                            fits.map((b) => (
                              <Badge key={b.batch_id} tone="slate" size="sm">
                                {b.name}
                              </Badge>
                            ))
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <Card data-testid="batches-card">
        <CardHeader
          icon={<Users className="h-5 w-5" aria-hidden />}
          title="Batches"
          description="A room must have at least as many seats as the batch has students."
        />
        <CardBody>
          <div className="scroll-thin overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full min-w-[320px] text-left" data-testid="batches-table">
              <thead className="bg-slate-50">
                <tr>
                  <th className="th">Batch</th>
                  <th className="th w-32 text-right">Students</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dataset.batches.map((b) => (
                  <tr key={b.batch_id}>
                    <td className="td !py-1.5">
                      <div className="px-2 font-medium text-slate-800">{b.name}</div>
                      <div className="px-2 text-[11px] text-slate-400">
                        {b.batch_id} {"·"} Sem {b.semester || "-"}
                      </div>
                    </td>
                    <td className="td !py-1.5">
                      <InlineEdit
                        type="number"
                        min={1}
                        max={10000}
                        align="right"
                        value={b.student_count}
                        ariaLabel={`Students in ${b.name}`}
                        testId={`batch-students-${b.batch_id}`}
                        validate={positiveInt}
                        onInvalid={invalid}
                        onCommit={(v) => void editBatch(b, { student_count: Number(v) })}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
