"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export interface TabDef {
  label: string;
  href: string;
  on?: boolean;
}

/** The three places there are to go. Everything the top bar used to hold —
 *  Feedback, Changelog, Docs — pointed at "#", and the "vincent · Pro" badge and
 *  avatar were decoration that also shipped the owner's name to every visitor of
 *  a hosted build. A nav item that does nothing is worse than no nav item. */
const NAV = [
  { label: "Decks", href: "/" },
  { label: "Import", href: "/import" },
  { label: "Results", href: "/results" },
];

/** Topbar + optional tab row. */
export function Chrome({
  context,
  contextImg,
  tabs,
}: {
  context?: string;
  contextImg?: string;
  tabs?: TabDef[];
}) {
  const path = usePathname() ?? "/";
  // "/" only matches exactly; the others match their whole subtree, so a replay
  // under /results/... still highlights Results.
  const isOn = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <header className="chrome">
      <div className="tb">
        <Link className="path" href="/">
          <svg className="glyph" viewBox="0 0 24 24" fill="none" aria-label="Sim Lab">
            <path d="M12 2 2.5 21.5h19L12 2Z" stroke="#EDEDED" strokeWidth="1.6" strokeLinejoin="round" />
            <path d="M12 8.5v6.5" stroke="#EDEDED" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
          Sim Lab
        </Link>
        {context && (
          <>
            <span className="slash">/</span>
            <div className="path">
              {contextImg && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={contextImg} alt="" onError={(e) => e.currentTarget.remove()} />
              )}
              {context}
            </div>
          </>
        )}
        <nav className="tb-links">
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
      </div>
      {tabs && tabs.length > 0 && (
        <nav className="tabs">
          {tabs.map((t) => (
            <Link key={t.label} className={`tab${t.on ? " on" : ""}`} href={t.href}>
              {t.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}

export function Footer({ right }: { right?: string }) {
  return (
    <footer className="chrome">
      <div className="ft">
        <span>Sim Lab is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy.</span>
        <span>Card images via Scryfall</span>
        {right && <span className="mono">{right}</span>}
      </div>
    </footer>
  );
}
