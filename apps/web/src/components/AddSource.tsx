"use client";

import { useRef, useState } from "react";
import { Loader2, Plus, UploadCloud } from "lucide-react";
import { buttonClass } from "@kb/ui";

// Generic "add a source" control: a file (drag/drop or browse) OR a link. No
// source-type-specific copy — the backend infers the type from the file/URL.
export function AddSource({
  onUploadFile,
  onIngestUrl,
  busy
}: {
  onUploadFile: (file: File) => void;
  onIngestUrl: (url: string) => void;
  busy: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [drag, setDrag] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function submitFile() {
    if (!file || busy) return;
    onUploadFile(file);
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  function submitUrl() {
    const trimmed = url.trim();
    if (!trimmed || busy) return;
    onIngestUrl(trimmed);
    setUrl("");
  }

  return (
    <div className="addsrc">
      <div
        className={`dropzone${drag ? " dropzone--drag" : ""}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) setFile(dropped);
        }}
      >
        <span className="dropzone__icon">
          <UploadCloud size={24} strokeWidth={1.5} />
        </span>
        {file ? (
          <div className="dropzone__main is-chosen">{file.name}</div>
        ) : (
          <>
            <div className="dropzone__main">Drop a PDF or browse</div>
            <div className="dropzone__sub">We&apos;ll extract, chunk, and embed it for you</div>
          </>
        )}
        <input
          ref={inputRef}
          type="file"
          hidden
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>

      {file ? (
        <button className={buttonClass({ variant: "primary", block: true })} onClick={submitFile} disabled={busy}>
          {busy ? <Loader2 size={15} className="spin" /> : <Plus size={15} />}
          Add this file
        </button>
      ) : null}

      <div className="or-row">or paste a link</div>

      <div className="url-row">
        <input
          className="saga-input"
          type="url"
          placeholder="https://youtube.com/watch?v=…"
          aria-label="Source URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitUrl();
          }}
        />
        <button
          className={buttonClass({ variant: "ghost" })}
          onClick={submitUrl}
          disabled={!url.trim() || busy}
        >
          Add
        </button>
      </div>
    </div>
  );
}
