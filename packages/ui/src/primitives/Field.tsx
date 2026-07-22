import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";
import { cn } from "../cn";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: ReactNode;
  error?: ReactNode;
}

/** Labelled text input. Label is always present (never placeholder-as-label) for accessibility. */
export function Field({ label, hint, error, className, id, ...rest }: Props) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const describedBy = error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined;
  return (
    <div className="saga-field">
      <label className="saga-label" htmlFor={inputId}>
        {label}
      </label>
      <input
        id={inputId}
        className={cn("saga-input", className)}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        {...rest}
      />
      {error ? (
        <span id={`${inputId}-error`} className="saga-field__error">
          {error}
        </span>
      ) : hint ? (
        <span id={`${inputId}-hint`} className="saga-field__hint">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
