import { formatLocator, typeCopy, type SourceType } from "@kb/shared";
import { DEMO_CITATIONS, DEMO_LIBRARY } from "./demo-content";
import { LOGIN_URL, REGISTER_URL } from "./config";

/**
 * Every word the marketing page shows, in one place.
 *
 * Copy may carry `<em>` (dimmed), `<span>` (accented) and `<br/>` (a line break the display
 * type depends on) - see `rich.tsx`. Section ids double as anchors, so `#how-it-works` and
 * `#privacy` keep resolving for links that predate this page.
 */

export type NavItem = { id: string; label: string; href: string };

export const SECTION = {
  about: "about",
  howItWorks: "how-it-works",
  library: "library",
  privacy: "privacy",
  getStarted: "get-started"
} as const;

export const NAVIGATION: NavItem[] = [
  { id: SECTION.howItWorks, label: "How it works", href: `#${SECTION.howItWorks}` },
  { id: SECTION.library, label: "Library", href: `#${SECTION.library}` },
  { id: SECTION.getStarted, label: "Get started", href: `#${SECTION.getStarted}` }
];

export const NAV_SPY: { id: string; label: string }[] = [
  { id: SECTION.about, label: "About" },
  { id: SECTION.howItWorks, label: "How it works" },
  { id: SECTION.library, label: "Library" },
  { id: SECTION.privacy, label: "Privacy" },
  { id: SECTION.getStarted, label: "Get started" }
];

export const ACCOUNT = {
  login: { label: "Log in", href: LOGIN_URL },
  register: { label: "Sign up", href: REGISTER_URL },
  groups: [
    { title: "New to Saga", label: "Create your account", href: REGISTER_URL },
    { title: "Already have one", label: "Log in", href: LOGIN_URL }
  ]
};

export const LOADER = { top: "Saga", bottom: "Cited answers" };

export const HERO = {
  title: "Answers you can trace<br/>back to the page.",
  description:
    "Saga reads your own <em>documents</em>, <em>slides</em>,<br/><em>notes</em>, <em>videos</em> and <em>recordings</em>, and lets you<br/>ask them questions in <em>plain language</em>.",
  scrollLabel: "Scroll to explore"
};

export const ABOUT =
  "Every sentence Saga gives back points at the passage it came from — the file, the page, the timestamp, the verbatim quote.<br/>When your library doesn’t contain the answer, Saga says so instead of inventing one.";

export const GROUNDING = {
  /** One line per kind of source; the highlighted one is where they fuse. */
  lines: [
    { label: "Answer", seed: 650, amplitude: 1, positionShift: 2, highlighted: true },
    { label: "Documents", seed: 350, amplitude: 2, positionShift: -3 },
    { label: "Slides", seed: 750, amplitude: 1.5, positionShift: -2 },
    { label: "Recordings", seed: 520, amplitude: 1.25, positionShift: -4 },
    { label: "Notes", seed: 880, amplitude: 1.75, positionShift: -1 }
  ],
  statement: "Saga only answers from passages it actually retrieved from your library.",
  title: "Grounded answers only.",
  text: "If not enough passages clear the relevance bar, you get a plainly-marked “not enough in your sources” response — not a confident paragraph assembled out of nothing.",
  cta: { label: "Create your account", href: REGISTER_URL }
};

export type Step = { index: string; title: string; text: string; media: "add" | "ask" | "cite" };

export const HOW_IT_WORKS = {
  title: "Put material in, ask a question, check the source.",
  text: "Five kinds of source, all searchable in the same breath. Adding one is instant; making it usable takes a moment, and Saga shows you where it is.",
  steps: [
    {
      index: "001",
      title: "Add your sources",
      text: "Drop in PDFs, slide decks, Markdown, MP3s, or paste a YouTube link. Saga reads the text, splits it into passages and indexes them.",
      media: "add"
    },
    {
      index: "002",
      title: "Ask in plain language",
      text: "Saga searches your library for the passages that actually bear on the question, and answers using only those. Follow-ups understand what came before.",
      media: "ask"
    },
    {
      index: "003",
      title: "Open the citation",
      text: "Click any citation and you land on the original — the cited page of the PDF, the deck at that slide, the recording at that second.",
      media: "cite"
    }
  ] satisfies Step[]
};

export type LibraryRow = { index: string; title: string; type: string; locator: string; sourceType: SourceType };

export const LIBRARY = {
  title: "The library<br/>behind it.",
  text: "Every source is <span>cited by</span> where its passage lives:<br/><span>the page of a PDF,</span> the slide of a deck,<br/><span>the second of a recording,</span> the section of your notes.",
  rows: DEMO_LIBRARY.map(
    (item, i): LibraryRow => ({
      index: String(i + 1).padStart(2, "0"),
      title: item.title,
      type: typeCopy[item.source_type].label,
      locator: `Cited by ${typeCopy[item.source_type].locator}`,
      sourceType: item.source_type
    })
  ),
  href: REGISTER_URL
};

/** The relevance rings in step two: the demo answer's own citations. */
export const RETRIEVAL = DEMO_CITATIONS.map((citation) => ({
  score: Math.round(citation.score * 100),
  label: formatLocator(citation.locator)
}));

export type PrivacyItem = { index: string; title: string; text: string; icon: "rows" | "lock" | "erase" | "model" };

export const PRIVACY = {
  title: "Your documents<br/>stay yours.",
  byline: "Private by construction",
  items: [
    {
      index: "01",
      title: "Row-level isolation",
      text: "Scoping is a database policy, not a WHERE clause someone can forget. Every account gets its own library, and it is only ever retrieved for you.",
      icon: "rows"
    },
    {
      index: "02",
      title: "Encrypted at rest",
      text: "Encrypted at rest and in transit: the original files, and the vectors derived from them.",
      icon: "lock"
    },
    {
      index: "03",
      title: "Deletion means deletion",
      text: "Removing a source removes its passages and its embeddings. Nothing of it stays behind to be found later.",
      icon: "erase"
    },
    {
      index: "04",
      title: "No training on it",
      text: "Your documents are never used to train models. Nothing you add leaves your library to teach anything else.",
      icon: "model"
    }
  ] satisfies PrivacyItem[]
};

export const CALL = {
  title: "Stop re-reading things<br/>you’ve already <span>read.</span>",
  text: "Build the library once. Ask it anything after that, and check the answer yourself in one click.",
  cta: { label: "Create your account", href: REGISTER_URL }
};

export const FOOTER = {
  marquee: "Ask your library",
  infosTitle: "Get started",
  links: ACCOUNT.groups,
  legal: ["Your library, isolated at the database", "No plans to pick"],
  credits: "Cited answers over your own sources"
};
