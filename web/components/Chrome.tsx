import Link from "next/link";

export interface TabDef {
  label: string;
  href: string;
  on?: boolean;
}

/** Topbar + optional tab row. Matches mockups/simlab_v3_*.html chrome exactly. */
export function Chrome({
  context,
  contextImg,
  tabs,
}: {
  context?: string;
  contextImg?: string;
  tabs?: TabDef[];
}) {
  return (
    <header className="chrome">
      <div className="tb">
        <svg className="glyph" viewBox="0 0 24 24" fill="none" aria-label="Sim Lab">
          <path d="M12 2 2.5 21.5h19L12 2Z" stroke="#EDEDED" strokeWidth="1.6" strokeLinejoin="round" />
          <path d="M12 8.5v6.5" stroke="#EDEDED" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="slash">/</span>
        <div className="path">
          <Link href="/">vincent</Link> <span className="plan">Pro</span>
        </div>
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
        <div className="tb-links">
          <a className="q" href="#">Feedback</a>
          <a className="q" href="#">Changelog</a>
          <a className="q" href="#">Docs</a>
          <div className="avatar" />
        </div>
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
