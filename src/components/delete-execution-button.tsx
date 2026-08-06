"use client";

import { deleteTradeAction } from "@/app/actions";

export function DeleteExecutionButton({ id }: { id: string }) {
  return (
    <form
      action={deleteTradeAction}
      onSubmit={(event) => {
        if (!window.confirm("Delete this execution? Your metrics will recalculate.")) {
          event.preventDefault();
        }
      }}
    >
      <input type="hidden" name="id" value={id} />
      <button className="delete-button" type="submit" title="Delete execution">
        Delete
      </button>
    </form>
  );
}
