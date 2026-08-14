import { cn } from "../cn";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)} aria-label="Saga">
      <svg viewBox="0 0 24 24" className="size-5 text-primary" aria-hidden>
        <path
          d="M12 2 3 7v10l9 5 9-5V7l-9-5Z"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path d="M8 12h8M12 8v8" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <span className="text-[17px] font-semibold tracking-[-0.02em]">Saga</span>
    </span>
  );
}
