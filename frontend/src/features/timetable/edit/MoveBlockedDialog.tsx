import { OctagonX, PencilLine } from "lucide-react";
import type { Conflict, Entry, MoveResult, Suggestion } from "../../../api";
import { Button, Modal } from "../../../components/ui";
import { dayName } from "../../../lib/format";
import type { Slot } from "../gridModel";
import { AffectedEntries, ConflictList, SuggestionChips } from "./MoveFeedback";

export interface BlockedMove {
  entry: Entry;
  target: Slot;
  result: MoveResult;
}

interface Props {
  blocked: BlockedMove | null;
  applying: boolean;
  onClose: () => void;
  /** apply one of the suggested alternatives straight away */
  onApply: (blocked: BlockedMove, s: Suggestion) => void;
  /** open the edit dialog (keyboard friendly) */
  onEdit: (blocked: BlockedMove) => void;
  onShowEntry: (entry: Entry, conflicts: Conflict[]) => void;
}

/** Shown when a dropped class would break a rule: explains why, names the clashing classes, offers alternatives. */
export function MoveBlockedDialog({ blocked, applying, onClose, onApply, onEdit, onShowEntry }: Props) {
  const b = blocked;
  return (
    <Modal
      open={!!b}
      onClose={onClose}
      size="md"
      title="Move blocked"
      subtitle={b ? `${b.entry.subject_name} (${b.entry.batch_name}) cannot go to ${dayName(b.target.day)}, Period ${b.target.period}.` : undefined}
      data-testid="move-blocked"
      footer={
        <>
          <Button onClick={() => b && onEdit(b)} icon={<PencilLine className="h-4 w-4" aria-hidden />} disabled={applying} data-testid="move-blocked-edit">
            Choose another slot
          </Button>
          <Button variant="primary" onClick={onClose} disabled={applying} data-testid="move-blocked-ok" data-autofocus>
            OK, leave it where it is
          </Button>
        </>
      }
    >
      {b && (
        <div className="space-y-4">
          <div className="space-y-2.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3">
            <p className="flex items-start gap-2 text-sm font-semibold text-red-900" data-testid="move-blocked-message">
              <OctagonX className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden />
              {b.result.conflicts.length === 1 ? "Moving it here would break a rule:" : `Moving it here would create ${b.result.conflicts.length} problems:`}
            </p>
            <ConflictList conflicts={b.result.conflicts} />
            <AffectedEntries entries={b.result.affected_entries} onShow={(e) => onShowEntry(e, b.result.conflicts)} />
          </div>
          {b.result.suggestions.length > 0 && (
            <SuggestionChips
              suggestions={b.result.suggestions}
              heading="Move it here instead"
              hint={applying ? "Moving..." : "Click an alternative to move the class there. It is conflict-free."}
              onPick={(s) => onApply(b, s)}
            />
          )}
          <p className="text-sm text-slate-600">
            <strong className="text-slate-900">Nothing was saved.</strong> The class is still on {dayName(b.entry.day)}, Period {b.entry.start_period}.
          </p>
        </div>
      )}
    </Modal>
  );
}
