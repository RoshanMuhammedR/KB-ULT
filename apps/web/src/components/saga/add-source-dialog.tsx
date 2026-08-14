"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ClipboardPaste, Link2, Upload, X } from "lucide-react";
import { typeCopy, type SourceType } from "@kb/shared";
import { Button, Input, Label, Pill, SourceIcon } from "@kb/ui";
import type { KnowledgeAsset } from "@/types/api";
import * as api from "@/lib/api";

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
  onClose,
  onAdded
}: {
  onClose: () => void;
  onAdded: (asset: KnowledgeAsset) => void;
}) {
  const [chosen, setChosen] = useState<SourceType | null>(null);
  const [url, setUrl] = useState("");
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const titleId = useId();

  const option = ADD_OPTIONS.find((item) => item.type === chosen);
  const isUpload = chosen !== null && chosen !== "youtube";

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** Each file is posted separately so one rejection can't take the others down with it. */
  async function uploadFiles(files: File[]) {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    const failures: string[] = [];

    for (const file of files) {
      try {
        onAdded(await api.uploadFile(file));
      } catch (err) {
        failures.push(
          `${file.name}: ${err instanceof Error ? err.message : "couldn't be added"}`
        );
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
      onAdded(await api.ingestUrl(url.trim()));
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
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-foreground/25 p-0 sm:items-center sm:p-6"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-t-xl border border-border bg-card p-6 sm:rounded-xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 id={titleId} className="text-display-sm">
              Add a source
            </h2>
            <p className="mt-1 text-[13px] text-muted-foreground">
              Adding is instant. Making it searchable takes a moment — you can keep working.
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="inline-flex size-8 items-center justify-center rounded-md border border-border"
          >
            <X className="size-4" />
          </button>
        </div>

        <Label className="mt-6">Choose a type</Label>
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {ADD_OPTIONS.map((item) => (
            <li key={item.type}>
              <button
                type="button"
                onClick={() => {
                  setChosen(item.type);
                  setError(null);
                }}
                aria-pressed={chosen === item.type}
                className={`flex w-full items-start gap-3 rounded-md border p-3 text-left transition-colors ${
                  chosen === item.type
                    ? "border-foreground"
                    : "border-border hover:border-border-strong"
                }`}
              >
                <SourceIcon type={item.type} className="size-8" />
                <span>
                  <span className="block text-[14px] font-semibold">
                    {typeCopy[item.type].label}
                  </span>
                  <span className="block text-[12px] text-muted-foreground">{item.how}</span>
                  <span className="mt-1 block text-[11px] text-muted-soft">{item.note}</span>
                </span>
              </button>
            </li>
          ))}
          <li>
            <div className="flex h-full items-center rounded-md border border-dashed border-border-strong p-3 text-[12px] text-muted-foreground">
              More types are added over time — the list isn&apos;t fixed.
            </div>
          </li>
        </ul>

        {chosen === "markdown" ? (
          <div className="mt-6 space-y-3">
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
              className="w-full rounded-md border border-border bg-canvas-soft p-3 font-mono text-[13px]"
            />
            <p className="text-[12px] text-muted-foreground">
              Or use the file picker below to upload a .md file instead.
            </p>
          </div>
        ) : chosen === "youtube" ? (
          <div className="mt-6">
            <Input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://youtube.com/watch?v=…"
              aria-label="YouTube link"
            />
          </div>
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
            className={`mt-6 rounded-md border border-dashed p-8 text-center transition-colors ${
              dragging ? "border-foreground bg-muted" : "border-border-strong bg-canvas-soft"
            }`}
          >
            <Upload className="mx-auto size-5 text-muted-foreground" aria-hidden />
            <p className="mt-3 text-sm font-medium">Drop your file here, or choose one</p>
            <p className="mt-1 text-[12px] text-muted-foreground">
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
          <p className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[13px] whitespace-pre-line text-destructive">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button disabled={!canSubmit || busy} onClick={() => void primaryAction()}>
            {busy ? "Adding…" : "Add to library"}
          </Button>
        </div>
        <p className="mt-3 text-[12px] text-muted-soft">
          <Pill>Private</Pill> Files stay in your library and are never used to train models.
        </p>
      </div>
    </div>
  );
}
