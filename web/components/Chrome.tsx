"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Mascot } from "@/components/Mascot";
import ApiBaseSetting from "@/components/ApiBaseSetting";
import { healthOnce } from "@/lib/api";
import { SERVER_DOWN, SHOW_OPS } from "@/lib/format";

export interface TabDef {
  label: string;
  href: string;
  on?: boolean;
}

/** Routes whose whole purpose is model generation. They are dark while the
 *  engine's /health says `llm` is false, which is production today, and a tab
 *  that leads to a page that cannot work is a dead end (tasks/26-ux-review.md,
 *  problem 6). Matched here rather than flagged on each page's TabDef so every
 *  tab row that links a coaching page is covered, including ones added later. */
const NEEDS_LLM = /\/coaching(?:[?#]|$)/;

/** Whether generation is switched on: null while unknown. */
export function useLlmLive(enabled = true): boolean | null {
  const [live, setLive] = useState<boolean | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    healthOnce()
      .then((h) => alive && setLive(h.llm === true))
      .catch(() => alive && setLive(false));
    return () => {
      alive = false;
    };
  }, [enabled]);
  return live;
}

/** The five places there are to go — every one a noun, every one a place.
 *
 *  Previously four: New run · Import · Results · Rules. Three things were wrong
 *  with that. "New run" was a verb, and the page behind it did two unrelated
 *  jobs (browse every deck, and configure a gauntlet). "Import" is one action
 *  performed on decks, not a peer of Results. And the deck pages and the
 *  playtest sandbox — whole modes of the product — had no address at all: the
 *  only routes in were a pill on a tile inside /new and a hover popover that is
 *  display:none below 980px, i.e. nothing on a phone.
 *
 *  Import still has a route; it is reached from /decks, where it is the primary. */
const NAV = [
  { label: "Decks", href: "/decks" },
  { label: "Simulate", href: "/new" },
  { label: "Playtest", href: "/playtest" },
  { label: "Results", href: "/results" },
  { label: "Rules", href: "/rules" },
];

/** Topbar + optional tab row.
 *
 *  There is deliberately no breadcrumb. The bar used to render
 *  `brand / <context>`, where context was always a restatement of the H1 forty
 *  pixels below it — duplication on desktop, and actively harmful on a narrow
 *  screen: `.path` is nowrap and `.tb-links` is margin-left:auto with no wrap
 *  rule, so the breadcrumb pushed the nav off the right edge. Measured at 533px
 *  on a run report, Results and Rules were unreachable and Import clipped
 *  mid-word. Where there is real hierarchy — a replay belongs to a run — the
 *  page renders a `.back` link, which is the affordance that actually helps. */
export function Chrome({
  tabs,
  noBrand,
}: {
  tabs?: TabDef[];
  /** Home renders the full masthead below, and Cinzel appears exactly once
   *  per page — so the top bar yields its wordmark there. */
  noBrand?: boolean;
}) {
  const path = usePathname() ?? "/";
  const [open, setOpen] = useState(false);
  const headerRef = useRef<HTMLElement>(null);
  // Only a tab row that links a model-backed page asks /health. Until the
  // answer arrives such tabs stay hidden: production has generation off, so
  // showing first and removing later would flash a dead tab at every player.
  const wantsLlm = !!tabs?.some((t) => NEEDS_LLM.test(t.href));
  const llmLive = useLlmLive(wantsLlm);
  const shownTabs = tabs?.filter((t) => llmLive === true || !NEEDS_LLM.test(t.href));

  // "/" only matches exactly; the others match their whole subtree, so a replay
  // under /results/... still highlights Results. /new is checked before /decks
  // because neither is a prefix of the other, but a deck opened from the picker
  // still lives under /decks and should light Decks, not Simulate.
  const isOn = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  // Navigating closes the sheet: without this, tapping a link leaves the menu
  // open over the page you just asked for.
  useEffect(() => setOpen(false), [path]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onDown = (e: PointerEvent) => {
      const t = e.target;
      if (t instanceof Node && headerRef.current?.contains(t)) return;
      setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [open]);

  return (
    <header className="chrome" ref={headerRef}>
      <div className="tb">
        <Link className="path brand" href="/" aria-label="Arcane Sim Lab home">
          <Mascot size={26} />
          {!noBrand && <span className="wordmark">Arcane Sim Lab</span>}
        </Link>
        <nav className="tb-links" aria-label="Main">
          {NAV.map((n) => (
            <Link
              key={n.href}
              className={`navlink${isOn(n.href) ? " on" : ""}`}
              href={n.href}
              aria-current={isOn(n.href) ? "page" : undefined}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        {/* The narrow-screen counterpart. CSS swaps which of the two is shown at
            720px; both are always in the DOM so there is no hydration flash. */}
        <button
          type="button"
          className="navbtn"
          aria-expanded={open}
          aria-controls="nav-sheet"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </div>
      {open && (
        <nav className="navsheet" id="nav-sheet" aria-label="Main">
          {NAV.map((n) => (
            <Link
              key={n.href}
              className={isOn(n.href) ? "on" : undefined}
              href={n.href}
              aria-current={isOn(n.href) ? "page" : undefined}
            >
              {n.label}
            </Link>
          ))}
          {/* The engine address is an operator setting: useful on a dev box
              pointing at another engine, meaningless to a player, and it put
              "Engine /engine Change" in the public phone menu. Dev builds only. */}
          {SHOW_OPS && (
            <>
              <div className="div" />
              <div className="navsheet-eng">
                <ApiBaseSetting onChanged={() => window.location.reload()} />
              </div>
            </>
          )}
        </nav>
      )}
      {shownTabs && shownTabs.length > 0 && (
        <nav className="tabs">
          {shownTabs.map((t) => (
            <Link key={t.label} className={`tab${t.on ? " on" : ""}`} href={t.href}>
              {t.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}

/** The footer carries the two legal obligations and nothing else.
 *
 *  It used to take a `right` prop, which every page filled with an address:
 *  "sim_20260801_193328.json", "atraxa_counters.dck", "rules_qa",
 *  "parser: convert_decklist.py", "job 4f2c…". A filename, port or job id is an
 *  address, not content — it belongs in one closed disclosure at the foot of
 *  the page it addresses, for the person who needs to find the file on disk. */
export function Footer() {
  return (
    <footer className="chrome">
      {/* Legal obligations (DESIGN_SYSTEM.md §9) — rendered at --ink-4, never below. */}
      <div className="ft">
        <span>Sim Lab is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy.</span>
        <span>Card images via Scryfall</span>
      </div>
    </footer>
  );
}

/** The one place an address is allowed to appear: closed by default, at the
 *  foot of the page it belongs to. */
export function PageDetails({ label = "Details", children }: { label?: string; children: React.ReactNode }) {
  return (
    <details className="details">
      <summary>{label}</summary>
      <div className="details-body">{children}</div>
    </details>
  );
}

/** The engine did not answer. One message for every page.
 *
 *  Pages used to print "Start it with python3 engine/mtg_engine.py serve 8484"
 *  to whoever was looking, on six pages. That is an instruction for the person
 *  running the server, so it now appears in dev builds only; players get a
 *  sentence about their own stuff and when to come back. */
export function EngineDown({
  className = "lede",
  onRetry,
}: {
  className?: string;
  /** Renders a "Try again" button. Omit on pages that already retry on a
   *  timer. */
  onRetry?: () => void;
}) {
  return (
    <>
      <p className={className}>
        {SHOW_OPS ? (
          <>
            The engine at the configured address isn&apos;t answering. Start it with{" "}
            <span className="mono">python3 engine/mtg_engine.py serve 8484</span>, then try
            again. (Dev builds only; players see: {SERVER_DOWN})
          </>
        ) : (
          SERVER_DOWN
        )}
      </p>
      {onRetry && (
        <p className="note">
          <button type="button" className="btn" onClick={onRetry}>
            Try again
          </button>
        </p>
      )}
    </>
  );
}
