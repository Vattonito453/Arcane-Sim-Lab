"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { ImportResponse } from "@/lib/types";
import { plural } from "@/lib/format";
import { Chrome, Footer } from "@/components/Chrome";

const SOURCES = ["Paste a list", "Moxfield URL", "Archidekt URL", "Upload .dck"];

const SAMPLE = [
  "1 Kilo, Apogee Mind (EOC) 3",
  "1 Adarkar Wastes (EOC) 147",
  "1 Adamantium Bonding Tank (SLD) 1741",
  "1 Alibou, Ancient Witness (EOC) 113",
  "1 All Will Be One (PONE) 118p",
  "1 Arcane Signet (EOC) 53",
  "1 Buried Ruin (EOC) 150",
  "1 Cascade Bluffs (EOC) 153",
  "1 Cayth, Famed Mechanist (M3C) 10",
  "1 Chaos Warp (EOC) 49",
  "1 Coretapper (EOC) 132",
  "1 Crystalline Crawler (EOC) 133",
  "1 Lux Cannon (EOC) 138",
  "1 Steel Overseer (EOC) 141",
  "1 Thopter Spy Network (EOC) 97",
  "# …85 more cards in the full Kilo list",
].join("\n");

interface ParsedLine {
  qty: number;
  name: string;
}

const BASICS = new Set(["plains", "island", "swamp", "mountain", "forest", "wastes"]);

function isBasic(name: string): boolean {
  return BASICS.has(name.toLowerCase().replace(/^snow-covered\s+/, ""));
}

/** Advisory client-side parse — the engine re-validates on save. */
function parseList(text: string): ParsedLine[] {
  const out: ParsedLine[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || line.startsWith("//")) continue;
    const m = line.match(/^(\d+)\s*[xX]?\s+(.+)$/);
    if (!m) continue;
    let name = m[2];
    name = name.replace(/\s*\*[A-Za-z]+\*\s*$/, ""); // foil markers like *F*
    name = name.replace(/\s*\([A-Za-z0-9]{2,6}\)\s*[\w★-]*\s*$/, ""); // (SET) 123p
    name = name.trim();
    if (name) out.push({ qty: Number(m[1]), name });
  }
  return out;
}

export default function ImportPage() {
  const [tab, setTab] = useState(0);
  const [text, setText] = useState("");
  const [name, setName] = useState("");
  const [nameEdited, setNameEdited] = useState(false);
  const [debounced, setDebounced] = useState("");
  const [busy, setBusy] = useState<"save" | "validate" | null>(null);
  const [resp, setResp] = useState<ImportResponse | null>(null);
  const [netErr, setNetErr] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(text), 400);
    return () => clearTimeout(t);
  }, [text]);

  // Deck name follows the first card until the user edits it themselves.
  useEffect(() => {
    if (nameEdited) return;
    const first = parseList(text)[0];
    setName(first ? first.name : "");
  }, [text, nameEdited]);

  const checks = useMemo(() => {
    const lines = parseList(debounced);
    const total = lines.reduce((s, l) => s + l.qty, 0);
    const seen = new Map<string, { display: string; qty: number }>();
    for (const l of lines) {
      if (isBasic(l.name)) continue;
      const k = l.name.toLowerCase();
      const cur = seen.get(k);
      if (cur) cur.qty += l.qty;
      else seen.set(k, { display: l.name, qty: l.qty });
    }
    const dups = [...seen.values()].filter((v) => v.qty > 1).map((v) => v.display);
    const dupSet = new Set(dups.map((d) => d.toLowerCase()));
    const commander = lines.length > 0 ? lines[0].name : null;
    return { lines, count: lines.length, total, dups, dupSet, commander };
  }, [debounced]);

  const lineCount = useMemo(() => text.split("\n").filter((l) => l.trim()).length, [text]);

  const submit = async (save: boolean) => {
    if (busy) return;
    setBusy(save ? "save" : "validate");
    setResp(null);
    setNetErr(null);
    try {
      const r = await api.importDeck(name.trim() || "Untitled deck", text, undefined, save);
      setResp(r);
    } catch (e) {
      setNetErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const report = resp?.ok ? resp.report : undefined;

  return (
    <>
      <Chrome context="Import a deck" />
      <div className="page narrow">
        <Link className="q back" href="/">
          ‹ Back to Sim Lab
        </Link>

        <div className="head">
          <div>
            <h1>Import a deck</h1>
            <div className="sub">
              From a Moxfield or Archidekt URL, an MTGO or Arena export, plain text, or a .dck
              file.
            </div>
          </div>
        </div>

        <p className="lede">
          Paste your list exactly as you have it — set codes, foil markers, collector numbers and
          single-line exports all parse. <b>Your text is never modified:</b> anything unrecognized
          is flagged with a suggested fix, and fixes apply only if you accept them.
        </p>

        <div className="srcs">
          {SOURCES.map((s, i) => (
            <button
              key={s}
              className={`src${tab === i ? " on" : ""}`}
              onClick={() => setTab(i)}
            >
              {s}
            </button>
          ))}
          <span className="sample">
            <a
              className="bl"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setTab(0);
                setText(SAMPLE);
                setResp(null);
                setNetErr(null);
              }}
            >
              Or load the sample Kilo deck
            </a>
          </span>
        </div>

        {tab !== 0 ? (
          <p className="note">
            {SOURCES[tab]} import is coming soon — the engine only takes pasted text today.{" "}
            <a
              className="bl"
              href="#"
              onClick={(e) => {
                e.preventDefault();
                setTab(0);
              }}
            >
              Paste a list instead
            </a>
          </p>
        ) : (
          <div className="cols">
            <div>
              <input
                className="txt"
                placeholder="Deck name"
                aria-label="Deck name"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  setNameEdited(true);
                }}
              />
              <div className="note">
                <textarea
                  className="paste"
                  spellCheck={false}
                  placeholder={"1 Kilo, Apogee Mind (EOC) 3\n1 Arcane Signet (EOC) 53\n…one card per line, Moxfield or Arena export format"}
                  value={text}
                  onChange={(e) => {
                    setText(e.target.value);
                    setResp(null);
                    setNetErr(null);
                  }}
                />
              </div>
              <div className="inmeta">
                <span>
                  <span className="mono">{lineCount}</span> lines
                </span>
                <span>checked as you type</span>
                <span>checks run 400 ms after you pause</span>
              </div>
            </div>

            <div>
              <div className="sh">
                <h2>Checks</h2>
                <span className="meta">
                  {checks.count > 0
                    ? `${checks.commander ?? "no commander"}, ${checks.total} cards`
                    : "advisory — the engine is authoritative"}
                </span>
              </div>

              {checks.count === 0 ? (
                <p className="note">Paste a list on the left and the checks run here as you type.</p>
              ) : (
                <>
                  <div className="ck">
                    <span className="lbl">
                      {checks.total} of 100 cards
                      {checks.total !== 100 && <small> — Commander decks run exactly 100</small>}
                    </span>
                    <span className={`res st ${checks.total === 100 ? "ok" : "warn"}`}>
                      <i />
                      {checks.total === 100 ? "Passed" : "Needs a look"}
                    </span>
                  </div>
                  <div className="ck">
                    {checks.dups.length === 0 ? (
                      <span className="lbl">
                        Singleton legal <small>— no duplicates outside basics</small>
                      </span>
                    ) : (
                      <span className="lbl">
                        {checks.dups.length} duplicated{" "}
                        {checks.dups.length === 1 ? "name" : "names"}{" "}
                        <small>
                          — {checks.dups.slice(0, 3).join(", ")}
                          {checks.dups.length > 3 ? ` + ${checks.dups.length - 3} more` : ""}
                        </small>
                      </span>
                    )}
                    <span className={`res st ${checks.dups.length === 0 ? "ok" : "warn"}`}>
                      <i />
                      {checks.dups.length === 0 ? "Passed" : "Needs a look"}
                    </span>
                  </div>
                  <div className="ck">
                    <span className="lbl">
                      Commander guess <small>— {checks.commander}</small>
                    </span>
                    <span className="res st ok">
                      <i />
                      Found
                    </span>
                  </div>
                </>
              )}

              {netErr && (
                <div className="ck">
                  <span className="lbl">{netErr}</span>
                  <span className="res st bad">
                    <i />
                    Failed
                  </span>
                </div>
              )}
              {resp && !resp.ok && (
                <div className="ck">
                  <span className="lbl">{resp.error ?? "The engine rejected this list."}</span>
                  <span className="res st bad">
                    <i />
                    Rejected
                  </span>
                </div>
              )}
              {report && (
                <div className="ck">
                  <span className="lbl">
                    Engine check{" "}
                    <small>
                      — {report.commander}, {report.main_count} of {report.expected} main-deck
                      cards
                      {report.sideboard_dropped > 0
                        ? `, ${report.sideboard_dropped} sideboard dropped`
                        : ""}
                      {report.duplicates_nonbasic.length > 0
                        ? `, duplicates: ${report.duplicates_nonbasic.slice(0, 3).join(", ")}`
                        : ""}
                    </small>
                  </span>
                  <span className={`res st ${report.ok ? "ok" : "warn"}`}>
                    <i />
                    {report.ok ? "Passed" : "Needs a look"}
                  </span>
                </div>
              )}

              {checks.count > 0 && (
                <p className="note">
                  These checks are advisory — the engine re-validates the full list when you save.
                </p>
              )}

              <div className="ctarow">
                <button
                  className="btn pri"
                  disabled={busy !== null || !text.trim()}
                  onClick={() => void submit(true)}
                >
                  {busy === "save" ? "Saving…" : "Save deck to engine"}
                </button>
                <button
                  className="btn"
                  disabled={busy !== null || !text.trim()}
                  onClick={() => void submit(false)}
                >
                  {busy === "validate" ? "Validating…" : "Validate only"}
                </button>
              </div>

              {resp?.ok && resp.saved && resp.file && (
                <p className="note">
                  <span className="st ok">
                    <i />
                    Saved as <span className="mono">{resp.file}</span>
                  </span>{" "}
                  <Link className="bl" href={`/?deck=${encodeURIComponent(resp.file)}`}>
                    Run a gauntlet with it →
                  </Link>
                </p>
              )}
              {/* What the deck is trying to do, before a single game is simmed.
                  Known combos matter for reading results later: Forge's AI does
                  not pilot loops, so a combo deck's win rate reads as a floor. */}
              {resp?.ok && resp.combos?.status === "ok" && (
                <div className="note">
                  {(resp.combos.included?.length ?? 0) > 0 ? (
                    <>
                      <span className="st warn">
                        <i />
                        {plural(resp.combos.included?.length ?? 0, "known combo")} in this list
                      </span>
                      {resp.combos.included?.map((c) => (
                        <span key={c.id} className="ctanote">
                          {" "}· {c.cards.join(" + ")}
                          {c.produces[0] ? ` (${c.produces[0].toLowerCase()})` : ""}
                        </span>
                      ))}
                      <span className="ctanote">
                        {" "}— sim win rates for this deck will be a floor, not a verdict:
                        the AI assembles combos but rarely fires them.
                      </span>
                    </>
                  ) : (
                    <span className="ctanote">
                      No known combos in this list
                      {(resp.combos.almost_included ?? 0) > 0 && (
                        <>
                          {" "}—{" "}
                          <span className="mono">{resp.combos.almost_included}</span> are one
                          card away (Commander Spellbook)
                        </>
                      )}
                      .
                    </span>
                  )}
                </div>
              )}
              {resp?.ok && resp.saved === false && (
                <p className="note">Validated only — nothing was saved to the engine.</p>
              )}

              <p className="note ctanote">Your text is never modified — fixes are suggestions.</p>
            </div>
          </div>
        )}
      </div>
      <Footer right="parser: convert_decklist.py" />
    </>
  );
}
