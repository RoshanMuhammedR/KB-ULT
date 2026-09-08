/**
 * The MIME type a dragged knowledge base is carried under.
 *
 * A custom type rather than `text/plain`: a base id dropped into a text field would otherwise
 * paste a raw UUID into whatever the user was writing. `text/plain` is set alongside it as a
 * courtesy for anything that only understands that, but the drop handler reads this one
 * first so it can tell a base apart from arbitrary dragged text.
 */
export const BASE_DRAG_TYPE = "application/x-saga-base";

/** Puts a base on a drag event under both types, and sets the copy cursor. */
export function setBaseDragData(event: React.DragEvent, baseId: string) {
  event.dataTransfer.setData(BASE_DRAG_TYPE, baseId);
  event.dataTransfer.setData("text/plain", baseId);
  event.dataTransfer.effectAllowed = "copy";
}

/** Reads a base id off a drop event, or null when the drop was something else. */
export function readBaseDragData(event: React.DragEvent): string | null {
  return event.dataTransfer.getData(BASE_DRAG_TYPE) || null;
}
