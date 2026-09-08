"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
  type ReactNode
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  Brain,
  Check,
  Columns2,
  Database,
  ShieldCheck,
  X
} from "lucide-react";
import { Button, Modal, ModalBody, ModalFooter, ModalHeader, cn } from "@kb/ui";

/**
 * The first-run walkthrough.
 *
 * Four steps, each describing something the product actually does — the tour is the first
 * promise Saga makes, and a tour that describes a feature nobody can find is worse than no
 * tour. Dismissed once, it stays dismissed; the "?" in the header is how it comes back.
 */
const SEEN_KEY = "saga.onboarding.seen";

type OnboardingValue = { start: () => void };

const OnboardingContext = createContext<OnboardingValue>({ start: () => {} });

export function useOnboarding(): OnboardingValue {
  return useContext(OnboardingContext);
}

const STEPS = [
  {
    badge: "Organise",
    title: "Separate knowledge bases",
    icon: Database,
    description:
      "Group your sources into bases — one per project, client or subject. A question is only ever answered from the bases you have attached, so a stray document in another base cannot leak into an answer.",
    points: [
      "Attach as many bases as you like to one question, and answers cite across all of them.",
      "Drag a base onto the Chat tab to attach it, or use the Attach button on any base card.",
      "A single source can belong to several bases without being uploaded or indexed twice."
    ]
  },
  {
    badge: "Trust",
    title: "Every claim carries its source",
    icon: ShieldCheck,
    description:
      "Answers cite the passage each claim came from, with a locator you can open: a page in a PDF, a slide in a deck, a heading in a document, a timestamp in audio.",
    points: [
      "Click a citation to open the exact passage in the source it came from.",
      "Each answer is checked sentence by sentence against the passages that were retrieved.",
      "When your sources do not cover the question, Saga says so instead of inventing an answer."
    ]
  },
  {
    badge: "Read",
    title: "The source, beside the answer",
    icon: Columns2,
    description:
      "Open any source without losing the thread. The reader keeps its own URL, so a passage you want someone else to see is a link you can send them.",
    points: [
      "The passage a citation points at is highlighted when the reader opens.",
      "The original file is always one click away, exactly as you uploaded it.",
      "Every source shows what happened during ingestion, including why one failed."
    ]
  },
  {
    badge: "Remember",
    title: "Durable memory, on your terms",
    icon: Brain,
    description:
      "Saga keeps a short list of standing facts about how you work, and uses them as background. It never cites them, and your documents always overrule them.",
    points: [
      "Everything remembered is listed in one place — readable, editable, deletable.",
      "Each answer says how many remembered facts it used.",
      "Nothing is remembered from a document; memory only holds what you have told it."
    ]
  }
] as const;

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  // On mount, not during render: localStorage does not exist on the server, and reading it
  // in the initial state would make the first client render disagree with the HTML.
  useEffect(() => {
    let seen = true;
    try {
      seen = window.localStorage.getItem(SEEN_KEY) === "1";
    } catch {
      // Blocked site data. Treating that as "seen" is the polite failure: a tour that cannot
      // remember being dismissed would otherwise reappear on every single load.
    }
    if (!seen) setOpen(true);
  }, []);

  const start = useCallback(() => setOpen(true), []);
  const value = useMemo(() => ({ start }), [start]);

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      {open ? <OnboardingModal onClose={() => setOpen(false)} /> : null}
    </OnboardingContext.Provider>
  );
}

function OnboardingModal({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [remember, setRemember] = useState(true);
  const titleId = useId();
  const active = STEPS[step]!;
  const Icon = active.icon;
  const last = step === STEPS.length - 1;

  function finish() {
    if (remember) {
      try {
        window.localStorage.setItem(SEEN_KEY, "1");
      } catch {
        // Nothing to do. The tour closes either way.
      }
    }
    onClose();
  }

  return (
    <Modal onClose={finish} size="md" labelledBy={titleId}>
      <ModalHeader>
        <div>
          <h2 id={titleId} className="text-sm font-semibold">
            Welcome to Saga
          </h2>
          <p className="text-[11px] text-muted-foreground">Cited answers over your own sources</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-surface-strong px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
            {step + 1} of {STEPS.length}
          </span>
          <button
            type="button"
            onClick={finish}
            aria-label="Close the tour"
            className="rounded-full p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" aria-hidden />
          </button>
        </div>
      </ModalHeader>

      <div className="flex gap-1 px-5 pt-4">
        {STEPS.map((item, index) => (
          <button
            key={item.title}
            type="button"
            onClick={() => setStep(index)}
            title={item.title}
            aria-label={`Step ${index + 1}: ${item.title}`}
            aria-current={index === step ? "step" : undefined}
            className={cn(
              "h-1.5 flex-1 rounded-full transition-colors",
              index === step
                ? "bg-primary"
                : index < step
                  ? "bg-primary/50"
                  : "bg-surface-strong hover:bg-border-strong"
            )}
          />
        ))}
      </div>

      <ModalBody className="space-y-4">
        <div className="flex items-start gap-3.5">
          <span className="shrink-0 rounded-2xl border border-border bg-background p-3 text-primary">
            <Icon className="size-6" aria-hidden />
          </span>
          <div>
            <span className="label-caps block text-primary">{active.badge}</span>
            <h3 className="mt-0.5 text-base font-bold">{active.title}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {active.description}
            </p>
          </div>
        </div>

        <ul className="space-y-2.5 rounded-xl border border-border bg-background p-4">
          {active.points.map((point) => (
            <li key={point} className="flex items-start gap-2 text-xs leading-normal">
              <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border border-border bg-card text-primary">
                <Check className="size-2.5" strokeWidth={3} aria-hidden />
              </span>
              {point}
            </li>
          ))}
        </ul>
      </ModalBody>

      <ModalFooter>
        <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={remember}
            onChange={(event) => setRemember(event.target.checked)}
            className="accent-primary"
          />
          Don&apos;t show this on launch
        </label>
        <div className="flex items-center gap-2">
          {step > 0 ? (
            <Button variant="secondary" size="sm" onClick={() => setStep((value) => value - 1)}>
              <ArrowLeft className="size-3.5" aria-hidden /> Back
            </Button>
          ) : null}
          <Button size="sm" onClick={() => (last ? finish() : setStep((value) => value + 1))}>
            {last ? "Get started" : "Next"}
            {last ? (
              <Check className="size-3.5" aria-hidden />
            ) : (
              <ArrowRight className="size-3.5" aria-hidden />
            )}
          </Button>
        </div>
      </ModalFooter>
    </Modal>
  );
}
