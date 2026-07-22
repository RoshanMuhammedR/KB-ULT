import Link from "next/link";
import { FileText, Youtube, Quote, ShieldCheck, Activity, Sparkles } from "lucide-react";
import { Divider, StatusDot, buttonClass } from "@kb/ui";
import { SiteNav } from "@/components/SiteNav";
import { SiteFooter } from "@/components/SiteFooter";

const STEPS = [
  {
    n: "01",
    title: "Add your sources",
    body: "Drop in a PDF or paste a YouTube link. Your library starts filling up in seconds."
  },
  {
    n: "02",
    title: "Saga ingests them",
    body: "Text is extracted, split into passages, and embedded in the background — you watch it happen live."
  },
  {
    n: "03",
    title: "Ask anything",
    body: "Chat with your library and get answers grounded in your own material, never the open web."
  }
];

const FEATURES = [
  {
    icon: Quote,
    title: "Source-cited answers",
    body: "Every answer carries the exact passages it came from — open the citation and verify it yourself."
  },
  {
    icon: FileText,
    title: "PDFs and video, together",
    body: "Documents and YouTube transcripts live in one searchable library, side by side."
  },
  {
    icon: Activity,
    title: "Live ingestion",
    body: "Follow each source from queued to ready, with honest, readable status when something fails."
  },
  {
    icon: ShieldCheck,
    title: "Private by default",
    body: "One isolated workspace per account. Your sources and answers never leave it."
  }
];

export default function LandingPage() {
  return (
    <>
      <SiteNav />

      <main>
        {/* Hero */}
        <section className="hero">
          <div className="saga-container hero__inner">
            <span className="saga-pill">
              <StatusDot tone="live" />
              Private workspace · Source-cited
            </span>
            <h1 className="saga-display hero__title">Answers you can trace back to the page.</h1>
            <p className="hero__sub">
              Saga turns your PDFs and YouTube links into a private knowledge base — then answers
              your questions with citations you can open and check.
            </p>
            <div className="hero__actions">
              <Link className={buttonClass({ variant: "primary" })} href="/register">
                Get started
                <Sparkles size={16} strokeWidth={1.5} />
              </Link>
              <Link className={buttonClass({ variant: "ghost" })} href="/login">
                Log in
              </Link>
            </div>
          </div>
        </section>

        <Divider />

        {/* How it works */}
        <section id="how" className="section">
          <div className="saga-container">
            <p className="saga-meta section__tag">How it works</p>
            <div className="steps">
              {STEPS.map((step) => (
                <article key={step.n} className="step">
                  <span className="step__n saga-meta">{step.n}</span>
                  <h3 className="step__title">{step.title}</h3>
                  <p className="step__body">{step.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <Divider />

        {/* Features */}
        <section id="features" className="section">
          <div className="saga-container">
            <p className="saga-meta section__tag">Why Saga</p>
            <div className="features">
              {FEATURES.map(({ icon: Icon, title, body }) => (
                <article key={title} className="feature">
                  <Icon className="feature__icon" size={28} strokeWidth={1.5} />
                  <h3 className="feature__title">{title}</h3>
                  <p className="feature__body">{body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <Divider />

        {/* CTA */}
        <section className="cta">
          <div className="saga-container cta__inner">
            <h2 className="saga-heading cta__title">Start your workspace.</h2>
            <p className="cta__sub">Create a workspace, add a source, and ask your first question.</p>
            <Link className={buttonClass({ variant: "primary" })} href="/register">
              Get started
              <Sparkles size={16} strokeWidth={1.5} />
            </Link>
          </div>
        </section>
      </main>

      <SiteFooter />
    </>
  );
}
