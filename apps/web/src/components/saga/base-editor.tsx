"use client";

import { useId, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import { Button, Field, Input, Modal, ModalBody, ModalFooter, ModalHeader, Textarea, cn } from "@kb/ui";
import { BASE_COLOURS, type BaseColour, type KnowledgeBase } from "@/types/api";
import { baseColour, baseInitial, swatchClass } from "@/lib/base-colour";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { toast } from "@/stores/toast-store";

/**
 * Create a base, or change one. The same three fields either way.
 *
 * Not a route: this is a form in flight, not a place. Giving it a URL would mean the Back
 * button silently discards half-typed text, and a link someone shared would open an empty
 * form rather than the thing they meant to show.
 */
export function BaseEditor({
  base,
  onClose,
  onSaved
}: {
  /** The base being edited, or null to create one. */
  base: KnowledgeBase | null;
  onClose: () => void;
  onSaved?: (base: KnowledgeBase) => void;
}) {
  const add = useKnowledgeBasesStore((state) => state.add);
  const edit = useKnowledgeBasesStore((state) => state.edit);
  const bases = useKnowledgeBasesStore((state) => state.bases);

  const [name, setName] = useState(base?.name ?? "");
  const [description, setDescription] = useState(base?.description ?? "");
  const [colour, setColour] = useState<BaseColour>(
    base ? baseColour(base) : BASE_COLOURS[bases.length % BASE_COLOURS.length]!
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement | null>(null);
  const titleId = useId();
  const nameId = useId();
  const descriptionId = useId();

  const clean = name.trim();

  async function save() {
    if (!clean || busy) return;
    setBusy(true);
    setError(null);
    try {
      if (base) {
        await edit(base.id, { name: clean, description: description.trim() || null, colour });
        onSaved?.({ ...base, name: clean, description: description.trim() || null, colour });
      } else {
        const created = await add(clean, { description: description.trim() || null, colour });
        onSaved?.(created);
      }
      onClose();
    } catch {
      // The one failure worth naming: the server rejects a duplicate name with a 409, and
      // "something went wrong" would leave the user retyping the same name.
      setError("Couldn't save that. Is another base already called this?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      onClose={onClose}
      size="sm"
      labelledBy={titleId}
      initialFocus={nameRef}
      dismissable={!busy}
    >
      <ModalHeader>
        <h2 id={titleId} className="text-sm font-semibold">
          {base ? "Edit knowledge base" : "New knowledge base"}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </ModalHeader>

      <ModalBody className="space-y-4">
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className={cn(
              "flex size-11 shrink-0 items-center justify-center rounded-xl text-lg font-bold text-white shadow-sm",
              swatchClass(colour)
            )}
          >
            {baseInitial(clean || "?")}
          </span>
          <p className="text-xs text-muted-foreground">
            How this base will look wherever it appears — in the switcher, on a citation, and
            beside every source filed in it.
          </p>
        </div>

        <Field label="Name" id={nameId} {...(error ? { error } : {})}>
          <Input
            id={nameId}
            ref={nameRef}
            value={name}
            maxLength={120}
            onChange={(event) => setName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") void save();
            }}
            placeholder="Onboarding, Q3 research, Contracts…"
          />
        </Field>

        <Field
          label="Description"
          id={descriptionId}
          hint="Optional. What belongs in here, so the next person can tell."
        >
          <Textarea
            id={descriptionId}
            rows={3}
            maxLength={500}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            className="text-sm"
          />
        </Field>

        <div>
          <span className="block text-sm font-semibold">Colour</span>
          <div className="mt-2 flex flex-wrap gap-2">
            {BASE_COLOURS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setColour(option)}
                aria-pressed={option === colour}
                aria-label={option}
                title={option}
                className={cn(
                  "flex size-8 items-center justify-center rounded-lg text-white transition-transform",
                  swatchClass(option),
                  option === colour ? "scale-110 ring-2 ring-foreground/40" : "hover:scale-105"
                )}
              >
                {option === colour ? <Check className="size-4" strokeWidth={3} aria-hidden /> : null}
              </button>
            ))}
          </div>
        </div>
      </ModalBody>

      <ModalFooter className="justify-end">
        <Button variant="secondary" size="sm" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button size="sm" onClick={() => void save()} disabled={busy || !clean}>
          {busy ? "Saving…" : base ? "Save changes" : "Create base"}
        </Button>
      </ModalFooter>
    </Modal>
  );
}

/**
 * Deleting a base is not reversible and takes its conversations and memories with it, so
 * the wording says exactly that, with the real numbers rather than a generic warning.
 */
export function useDeleteBase() {
  const remove = useKnowledgeBasesStore((state) => state.remove);
  return async (base: KnowledgeBase) => {
    try {
      await remove(base.id);
      toast.success(`Deleted “${base.name}”`);
      return true;
    } catch {
      toast.error("Couldn't delete that base. It may be the only one left.");
      return false;
    }
  };
}
