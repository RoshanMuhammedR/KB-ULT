import type { ComponentProps, ReactNode } from "react";
import { cn } from "../cn";

export function Label({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("label-caps text-muted-foreground", className)}>{children}</div>;
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("hairline-panel", className)}>{children}</div>;
}

export type PillTone = "neutral" | "primary" | "success" | "danger";

export function Pill({
  children,
  className,
  tone = "neutral"
}: {
  children: ReactNode;
  className?: string;
  tone?: PillTone;
}) {
  const tones: Record<PillTone, string> = {
    neutral: "bg-surface-strong text-foreground",
    primary: "bg-primary/10 text-primary",
    success: "bg-success/12 text-success",
    danger: "bg-destructive/10 text-destructive"
  };
  return (
    <span
      className={cn(
        "label-caps inline-flex items-center gap-1.5 rounded-full px-2.5 py-1",
        tones[tone],
        className
      )}
    >
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  error,
  id,
  children
}: {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  id: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-semibold">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-[13px] text-destructive" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[13px] text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-md border border-border bg-card px-4 text-base text-foreground placeholder:text-muted-soft",
        className
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(
        "w-full rounded-md border border-border bg-card px-4 py-3 text-base text-foreground placeholder:text-muted-soft",
        className
      )}
      {...props}
    />
  );
}

export function Divider({ className }: { className?: string }) {
  return <hr className={cn("border-0 border-t border-border", className)} />;
}
