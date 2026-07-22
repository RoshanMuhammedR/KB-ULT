import type { ButtonHTMLAttributes } from "react";
import { cn } from "../cn";

export type ButtonVariant = "primary" | "ghost";

/** Shared class string for buttons AND link-buttons (e.g. Next <Link className={buttonClass()}>). */
export function buttonClass(opts: {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  block?: boolean;
  className?: string;
} = {}): string {
  const { variant = "primary", size = "md", block = false, className } = opts;
  return cn(
    "saga-btn",
    variant === "primary" ? "saga-btn--primary" : "saga-btn--ghost",
    size === "sm" && "saga-btn--sm",
    block && "saga-btn--block",
    className
  );
}

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "md" | "sm";
  block?: boolean;
}

export function Button({
  variant = "primary",
  size = "md",
  block = false,
  className,
  type = "button",
  ...rest
}: Props) {
  return (
    <button type={type} className={buttonClass({ variant, size, block, className })} {...rest} />
  );
}
