"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ClipboardPaste, Link2, Upload, X } from "lucide-react";
import { typeCopy, type SourceType } from "@kb/shared";
import {
  Button,
  Input,
  Label,
  Modal,
  ModalBody,
  ModalFooter,
  ModalHeader,
  Pill,
  SourceIcon,
  cn
} from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";
import { baseInitial, baseTileClass } from "@/lib/base-colour";
import { useKnowledgeBasesStore } from "@/stores/knowledge-bases-store";
import { useSourcesStore } from "@/stores/sources-store";

const ADD_OPTIONS: {
  type: SourceType;
  how: string;
  icon: typeof Upload;
  note: string;
  accept?: string;
}[] = [
  {
    type: "pdf",
    how: "Upload a file",
    icon: Upload,
    note: "Needs a text layer, not a scan",
    accept: ".pdf"
  },
  {
    type: "pptx",
    how: "Upload a deck",
    icon: Upload,
    note: "Slide text and speaker notes",
    accept: ".pptx"
  },
  {
    type: "audio",
    how: "Upload a recording",
    icon: Upload,
    note: "Transcribed — takes a few minutes",
    accept: ".mp3,.m4a,.wav,.ogg,.webm"
  },
  {
    type: "markdown",
    how: "Upload or paste",
    icon: ClipboardPaste,
    note: "Give pasted text a title",
    accept: ".md,.markdown"
  },
  { type: "youtube", how: "Paste a link", icon: Link2, note: "Needs transcripts enabled" }
];

/** Filename-safe slug for a pasted note. */
function slug(title: string): string {
  const base = title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return base || "note";
}

export function AddSourceDialog({
  knowledgeBaseId,
  onClose,
  onAdded
}: {
  /**
   * Where the source lands. Omitted on the Library tab, where the dialog asks — a source has
   * to belong somewhere specific, and "wherever the workspace default happens to be" is not
   * an answer anyone would recognise.
   */
  knowledgeBaseId?: string;
  onClose: () => void;
  onAdded?: (asset: KnowledgeAsset) => void;
}) {
  const bases = useKnowledgeBasesStore((state) => state.bases);
  const selectedId = useKnowledgeBasesStore((state) => state.selectedId);
  const track = useSourcesStore((state) => state.track);

  const [target, setTarget] = useState<string | null>(knowledgeBaseId ?? selectedId);
  const [chosen, setChosen] = useState<SourceType | null>(null);
  const [url, setUrl] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const titleId = useId();

  // The store loads after first paint on a cold start, so a dialog opened immediately would
  // have no base to offer. Adopt the first one as soon as there is one.
  useEffect(() => {
    if (!target && selectedId) setTarget(selectedId);
  }, [target, selectedId]);

  const option = ADD_OPTIONS.find((item) => item.type === chosen);
  const isUpload = chosen !== null && chosen !== "youtube";

  function accept(asset: KnowledgeAsset) {
    // Always into the library, so the count in the header and the Library tab move even when
    // the caller only wanted to know about it. `track` also starts following its ingestion.
    track(asset);
    onAdded?.(asset);
  }

  /** Each file is posted separately so one rejection can't take the others down with it. */
  async function uploadFiles(files: File[]) {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    const failures: string[] = [];

    for (const file of files) {
      try {
        accept(await api.uploadFile(file, target));
      } catch (err) {
        failures.push(`${file.name}: ${err instanceof Error ? err.message : "couldn't be added"}`);
      }
    }

    setBusy(false);
    if (failures.length > 0) {
      setError(failures.join("\n"));
      return;
    }
    onClose();
  }

  async function submitUrl() {
    if (!url.trim()) return;
    setBusy(true);
    setError(null);
    try {
      accept(await api.ingestUrl(url.trim(), target));
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That link couldn't be added.");
    } finally {
      setBusy(false);
    }
  }

  /** Pasted Markdown needs no endpoint of its own — it becomes a .md file upload. */
  async function submitNote() {
    const body = noteBody.trim();
    if (!body) return;
    const title = noteTitle.trim() || "Pasted note";
    const withHeading = body.startsWith("#") ? body : `# ${title}\n\n${body}`;
    const file = new File([withHeading], `${slug(title)}.md`, { type: "text/markdown" });
    await uploadFiles([file]);
  }

  function primaryAction() {
    if (chosen === "youtube") return submitUrl();
    if (chosen === "markdown" && noteBody.trim()) return submitNote();
    fileInput.current?.click();
    return Promise.resolve();
  }

  const canSubmit =
    chosen === "youtube" ? url.trim().length > 0 : chosen === "markdown" || chosen !== null;

  return (
    <Modal onClose={onClose} size="md" labelledBy={titleId} dismissable={!busy}>
      <ModalHeader>
        <div>
          <h2 id={titleId} className="text-sm font-semibold">
            Add a source
          </h2>
          <p className="text-[11px] text-muted-foreground">
            Adding is instant. Making it searchable takes a moment — you can keep working.
          </p>
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="size-4" aria-hidden />
        </button>
      </ModalHeader>

      <ModalBody className="space-y-6">
        {knowledgeBaseId ? null : (
          <div>
            <Label>Add it to</Label>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {bases.map((base) => (
                <button
                  key={base.id}
                  type="button"
                  onClick={() => setTarget(base.id)}
                  aria-pressed={base.id === target}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border py-1 pl-1 pr-2.5 text-xs font-medium transition-colors",
                    base.id === target
                      ? "border-primary bg-primary-soft text-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "flex size-5 items-center justify-center rounded-full text-[10px] font-bold text-white",
                      baseTileClass(base)
                    )}
                  >
                    {baseInitial(base.name)}
                  </span>
                  {base.name}
                </button>
              ))}
            </div>
          </div>
        )}

        <div>
          <Label>Choose a type</Label>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {ADD_OPTIONS.map((item) => (
              <li key={item.type}>
                <button
                  type="button"
                  onClick={() => {
                    setChosen(item.type);
                    setError(null);
                  }}
                  aria-pressed={chosen === item.type}
                  className={cn(
                    "flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors",
                    chosen === item.type
                      ? "border-primary bg-primary-soft/40"
                      : "border-border hover:border-border-strong"
                  )}
                >
                  <SourceIcon type={item.type} className="size-8" />
                  <span>
                    <span className="block text-[13px] font-semibold">
                      {typeCopy[item.type].label}
                    </span>
                    <span className="block text-[11px] text-muted-foreground">{item.how}</span>
                    <span className="mt-1 block text-[11px] text-muted-soft">{item.note}</span>
                  </span>
                </button>
              </li>
            ))}
            <li>
              <div className="flex h-full items-center rounded-xl border border-dashed border-border-strong p-3 text-[11px] text-muted-foreground">
                More types are added over time — the list isn&apos;t fixed.
              </div>
            </li>
          </ul>
        </div>

        {chosen === "markdown" ? (
          <div className="space-y-3">
            <Input
              value={noteTitle}
              onChange={(event) => setNoteTitle(event.target.value)}
              placeholder="Title for this note"
              aria-label="Title for pasted Markdown"
            />
            <textarea
              rows={5}
              value={noteBody}
              onChange={(event) => setNoteBody(event.target.value)}
              aria-label="Paste Markdown"
              placeholder="# Meeting notes&#10;Paste Markdown here…"
              className="w-full rounded-md border border-border bg-background p-3 font-mono text-[13px]"
            />
            <p className="text-[11px] text-muted-foreground">
              Or use the file picker below to upload a .md file instead.
            </p>
          </div>
        ) : chosen === "youtube" ? (
          <Input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://youtube.com/watch?v=…"
            aria-label="YouTube link"
          />
        ) : null}

        {isUpload ? (
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragging(false);
              void uploadFiles(Array.from(event.dataTransfer.files));
            }}
            className={cn(
              "rounded-xl border border-dashed p-8 text-center transition-colors",
              dragging ? "border-primary bg-primary-soft/40" : "border-border-strong bg-background"
            )}
          >
            <Upload className="mx-auto size-5 text-muted-foreground" aria-hidden />
            <p className="mt-3 text-sm font-medium">Drop your file here, or choose one</p>
            <p className="mt-1 text-[11px] text-muted-foreground">
              You can add several at once. Each is prepared independently.
            </p>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept={option?.accept}
              className="sr-only"
              onChange={(event) => {
                void uploadFiles(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              className="mt-4"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              {busy ? "Adding…" : "Choose file"}
            </Button>
          </div>
        ) : null}

        {error ? (
          <p className="whitespace-pre-line rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[13px] text-destructive">
            {error}
          </p>
        ) : null}

        <p className="text-[11px] text-muted-soft">
          <Pill>Private</Pill> Files stay in your library and are never used to train models.
        </p>
      </ModalBody>

      <ModalFooter className="justify-end">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button size="sm" disabled={!canSubmit || busy} onClick={() => void primaryAction()}>
          {busy ? "Adding…" : "Add source"}
        </Button>
      </ModalFooter>
    </Modal>
  );
}
