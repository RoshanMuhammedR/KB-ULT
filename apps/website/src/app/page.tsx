import {
  ArrowRight,
  BookOpenCheck,
  Quote,
  Search,
  ShieldCheck,
  Sparkles,
  Upload
} from "lucide-react";
import { typeCopy } from "@kb/shared";
import { Label, Panel, Pill, SourceIcon, StatusBadge, buttonClass } from "@kb/ui";
import { AnswerDemo } from "@/components/saga/answer-demo";
import { SiteLayout } from "@/components/saga/site-chrome";
import { DEMO_INSUFFICIENT, DEMO_LIBRARY } from "@/lib/demo-content";
import { LOGIN_URL, REGISTER_URL } from "@/lib/config";

const STEPS = [
  {
    icon: Upload,
    title: "Add what you're working from",
    body: "Drop in PDFs, slide decks, Markdown, MP3s, or paste a YouTube link. Saga reads the text, splits it into passages and indexes them. You can keep working while it does."
  },
  {
    icon: Search,
    title: "Ask in plain language",
    body: "Saga searches your library for the passages that actually bear on the question, and answers using only those. Follow-ups understand what came before."
  },
  {
    icon: BookOpenCheck,
    title: "Open the citation",
    body: "Click any citation and you land on the original — the cited page of the PDF, the deck at that slide, the recording at that second, with the surrounding context intact."
  }
];

const PRIVACY = [
  [
    "Row-level isolation",
    "Scoping is a database policy, not a WHERE clause someone can forget."
  ],
  ["Encrypted at rest and in transit", "Original files and the vectors derived from them."],
  ["Deletion means deletion", "Removing a source removes its passages and its embeddings."],
  ["No training on your material", "Your documents are never used to train models."]
];

export default function LandingPage() {
  return (
    <SiteLayout>
      <section className="border-b border-border">
        <div className="mx-auto max-w-6xl px-5 pt-20 pb-16">
          <Pill tone="primary">
            <Sparkles className="size-3" aria-hidden /> Grounded answers only
          </Pill>
          <h1 className="mt-6 max-w-4xl text-[2.75rem] leading-[1.06] tracking-[-0.03em] md:text-display-mega">
            Answers you can trace back to the page.
          </h1>
          <p className="mt-6 max-w-2xl text-[17px] leading-relaxed text-muted-foreground">
            Saga reads your own documents, slides, notes, videos and recordings, and lets you ask
            them questions in plain language. Every sentence it gives back points at the passage it
            came from — the file, the page, the timestamp, the verbatim quote. When your library
            doesn&apos;t contain the answer, Saga says so instead of inventing one.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <a href={REGISTER_URL} className={buttonClass("primary", "lg")}>
              Create your account <ArrowRight className="size-4" aria-hidden />
            </a>
            <a href="#how-it-works" className={buttonClass("secondary", "lg")}>
              See how it works
            </a>
          </div>
          <p className="mt-4 text-[13px] text-muted-foreground">
            Email and password, or Google. Your library, private to you. No plans to pick.
          </p>
        </div>
      </section>

      {/* Show the product rather than describe it */}
      <section className="border-b border-border bg-canvas-soft">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <Label>A real answer, with its receipts</Label>
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.35fr_1fr]">
            <AnswerDemo />
            <Panel className="p-6">
              <h2 className="text-display-sm">The library behind it</h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Five kinds of source, all searchable in the same breath. Adding one is instant;
                making it usable takes a moment, and Saga shows you where it is.
              </p>
              <ul className="mt-5 space-y-3">
                {DEMO_LIBRARY.map((item) => (
                  <li key={item.title} className="flex items-center gap-3">
                    <SourceIcon type={item.source_type} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{item.title}</span>
                      <span className="block text-[13px] text-muted-foreground">
                        {typeCopy[item.source_type].label} · cited by{" "}
                        {typeCopy[item.source_type].locator}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-5 flex flex-wrap gap-2 border-t border-border pt-5">
                <StatusBadge status="embedding" />
                <StatusBadge status="failed" />
                <StatusBadge status="ready" />
              </div>
            </Panel>
          </div>
        </div>
      </section>

      <section id="how-it-works" className="scroll-mt-16 border-b border-border">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <Label>Three steps</Label>
          <h2 className="mt-4 max-w-2xl text-display-lg">
            Put material in, ask a question, check the source.
          </h2>
          <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-border bg-border md:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.title} className="bg-card p-7">
                <step.icon className="size-5 text-primary" strokeWidth={1.75} aria-hidden />
                <h3 className="mt-4 text-[18px] font-semibold">{step.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="border-b border-border bg-canvas-soft">
        <div className="mx-auto grid max-w-6xl gap-10 px-5 py-20 md:grid-cols-2">
          <div>
            <Label>Honesty is a feature</Label>
            <h2 className="mt-4 text-display-lg">
              If your sources don&apos;t answer it, Saga tells you.
            </h2>
            <p className="mt-4 text-[16px] leading-relaxed text-muted-foreground">
              Saga only answers from passages it actually retrieved from your library. If not
              enough of them clear the relevance bar, you get a plainly-marked &ldquo;not enough in
              your sources&rdquo; response — not a confident paragraph assembled out of nothing. It
              reads differently from an answer, and differently from an error, because it is
              neither.
            </p>
          </div>
          <Panel className="p-6">
            <Pill>Not enough in your sources</Pill>
            <p className="mt-4 text-[15px] leading-relaxed">{DEMO_INSUFFICIENT}</p>
            <p className="mt-4 text-[13px] text-muted-foreground">
              Add a source that covers it, or rephrase the question.
            </p>
          </Panel>
        </div>
      </section>

      <section id="privacy" className="scroll-mt-16 border-b border-border">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <div className="grid gap-10 md:grid-cols-[1fr_1.2fr]">
            <div>
              <Label>Private by construction</Label>
              <h2 className="mt-4 text-display-lg">Your documents stay yours.</h2>
              <p className="mt-4 text-[16px] leading-relaxed text-muted-foreground">
                Every account gets its own isolated library, enforced at the database level rather
                than in application code. Your sources, passages and conversations are only ever
                retrieved for you. Delete a source and its passages go with it. Nothing you add is
                used to train models.
              </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {PRIVACY.map(([title, body]) => (
                <Panel key={title} className="p-5">
                  <ShieldCheck className="size-4 text-success" strokeWidth={1.75} aria-hidden />
                  <h3 className="mt-3 text-[16px] font-semibold">{title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-muted-foreground">{body}</p>
                </Panel>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section>
        <div className="mx-auto max-w-6xl px-5 py-24 text-center">
          <Quote className="mx-auto size-5 text-primary" strokeWidth={1.75} aria-hidden />
          <h2 className="mx-auto mt-6 max-w-2xl text-display-lg">
            Stop re-reading things you&apos;ve already read.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[16px] text-muted-foreground">
            Build the library once. Ask it anything after that, and check the answer yourself in
            one click.
          </p>
          <div className="mt-8 flex justify-center gap-3">
            <a href={REGISTER_URL} className={buttonClass("primary", "lg")}>
              Create your account
            </a>
            <a href={LOGIN_URL} className={buttonClass("secondary", "lg")}>
              Log in
            </a>
          </div>
        </div>
      </section>
    </SiteLayout>
  );
}
