"use client";

/** "Flag this moment" (repair plan WS2 layer A task 5, decision 11).
 *
 *  A playtester marks the replay moment on screen and says what looks wrong;
 *  the engine files it in the human review queue (POST /flags), which the
 *  owner triages weekly and the nightly reviewer reads first.
 *
 *  The flag follows the playhead while the form is open, so stepping the
 *  replay moves it, and the moment it will be filed against is spelled out
 *  above the fields: event number, round, whose turn, and the log line itself
 *  (the event log is the authoritative record on both board paths, so the
 *  flag anchors to it, never to the folded table).
 *
 *  The flags-only key (MTG_FLAG_KEYS) is saved in this browser under its own
 *  storage key once a flag is accepted, and lib/api sendFlag() is the only
 *  code that ever sends it. It is a secondary action: plain .btn, never the
 *  page's primary ("Watch the ...", or the play button when that is absent). */

import { useEffect, useId, useRef, useState } from "react";
import { FlagError, saveFlagKey, savedFlagKey, sendFlag } from "@/lib/api";
import { stripAi } from "@/lib/format";
import type { Step } from "@/lib/replay";

const NOTE_MAX = 1000; // engine FLAG_NOTE_MAX

/** The seat a log line is about: the first seat it names, else whoever's turn
 *  it is. A guess from text, so the form shows it as an editable default. */
function seatNamedIn(text: string, players: string[], active: string): string {
  let best = "";
  let at = Infinity;
  for (const p of players) {
    const name = stripAi(p);
    const i = name ? text.indexOf(name) : -1;
    if (i >= 0 && i < at) {
      at = i;
      best = p;
    }
  }
  return best || active || "";
}

/** Plain-language reason a flag did not go through. */
function explain(e: unknown, hadKey: boolean): string {
  if (!(e instanceof FlagError)) return "Something went wrong. Try again in a moment.";
  const msg = e.message;
  switch (e.status) {
    case 0:
      return "Could not reach the engine. Check your connection and try again.";
    case 401:
      return hadKey
        ? "That flag key was not recognised. Check it with whoever gave it to you."
        : "Enter your flag key first. The Sim Lab owner gives one to each playtester.";
    case 403:
      return "That key cannot flag moments.";
    case 404:
      return /unknown endpoint/.test(msg)
        ? "This engine does not take flags yet (it may be an older version)."
        : "This run is no longer on the server, so it cannot be flagged.";
    case 409:
      return "This replay is out of date. Reload the page and flag the moment again.";
    case 413:
      return `The note is too long. Keep it to ${NOTE_MAX.toLocaleString()} characters.`;
    case 429: {
      const mins = Math.max(1, Math.ceil(e.retryAfter / 60));
      return `That is a lot of flags for one hour. Try again in about ${mins} minute${mins === 1 ? "" : "s"}.`;
    }
    case 400:
      // The engine's wording names request fields ("anchor.event_index"); a
      // player gets the remedy instead. A 400 here means this page sent
      // something the engine could not place, which a reload fixes.
      return "The engine could not place this flag. Reload the replay and try again.";
    default:
      return "Something went wrong on the engine. Try again in a moment.";
  }
}

export function FlagMoment({
  id,
  file,
  game,
  step,
  index,
  total,
  players,
  name = stripAi,
  onClose,
}: {
  id: string;
  file: string;
  game: number;
  step: Step;
  index: number;
  total: number;
  /** The game's player keys, in the order to offer them: the replay passes
   *  the run page's order, so the seats read the same way on both pages. */
  players: string[];
  /** A seat's one name (shortName, the name the run title and the stories
   *  use). The option values stay the raw player keys the engine checks. */
  name?: (player: string) => string;
  onClose: () => void;
}) {
  const uid = useId();
  const [note, setNote] = useState("");
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [player, setPlayer] = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState<{ event: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [keyError, setKeyError] = useState<string | null>(null);
  const noteRef = useRef<HTMLTextAreaElement | null>(null);
  const keyRef = useRef<HTMLInputElement | null>(null);

  // After mount: storage is browser-only, and focus goes where the typing starts.
  useEffect(() => {
    const k = savedFlagKey();
    setKey(k);
    setSaved(Boolean(k));
    noteRef.current?.focus();
  }, []);

  // The seat follows the moment, like the rest of the anchor.
  const guessed = seatNamedIn(step.text, players, step.active);
  useEffect(() => {
    setPlayer(guessed);
  }, [index, guessed]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (sending) return;
    setError(null);
    setKeyError(null);
    setSent(null);
    const k = key.trim();
    setSending(true);
    try {
      await sendFlag(
        {
          run: file,
          game,
          anchor: { event_index: index, event_seq: step.seq, turn: step.turn, player: player || null },
          note,
        },
        k,
      );
      // Saved only once the engine has accepted it, so a mistyped key is
      // never remembered.
      if (k) {
        saveFlagKey(k);
        setSaved(true);
      }
      setSent({ event: index + 1 });
      setNote("");
    } catch (err) {
      const msg = explain(err, Boolean(k));
      if (err instanceof FlagError && err.status === 401) {
        setKeyError(msg);
        keyRef.current?.focus();
      } else {
        setError(msg);
      }
    } finally {
      setSending(false);
    }
  }

  const forget = () => {
    saveFlagKey("");
    setKey("");
    setSaved(false);
    keyRef.current?.focus();
  };

  const turnName = name(step.active);
  return (
    <form
      id={id}
      className="flagbox"
      aria-labelledby={`${uid}-h`}
      onSubmit={submit}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onClose();
        }
      }}
      noValidate
    >
      <div className="sh">
        <h2 id={`${uid}-h`}>Flag this moment</h2>
        <span className="meta">read in the weekly review</span>
      </div>
      <p className="flag-where">
        Event <span className="mono">{index + 1}</span> of{" "}
        <span className="mono">{total.toLocaleString()}</span> in game {game}
        {/* "Turn", the table turn, as the game story, the transport and the
            out seats count it; the engine still stores it as `round`. */}
        {step.round > 0 ? (
          <>
            , turn <b>{step.round}</b>. <b>{turnName}</b> is the active player.
          </>
        ) : (
          <>, before the first turn.</>
        )}{" "}
        Step the replay to move the flag.
      </p>
      <p className="flag-line">{step.text}</p>

      <label className="field-label" htmlFor={`${uid}-note`}>
        What looks wrong? (optional)
      </label>
      <textarea
        id={`${uid}-note`}
        ref={noteRef}
        className="flag-note"
        rows={4}
        maxLength={NOTE_MAX}
        value={note}
        aria-describedby={`${uid}-count`}
        onChange={(e) => {
          setNote(e.target.value);
          setSent(null);
        }}
      />
      <p className="field-hint" id={`${uid}-count`}>
        <span className="mono">{note.length}</span> of {NOTE_MAX.toLocaleString()} characters. What
        would you have done instead?
      </p>

      <div className="flag-grid">
        <div>
          <label className="field-label" htmlFor={`${uid}-seat`}>
            Whose play
          </label>
          <select
            id={`${uid}-seat`}
            className="flag-field"
            value={player}
            aria-describedby={`${uid}-seathint`}
            onChange={(e) => setPlayer(e.target.value)}
          >
            {players.map((p) => (
              <option key={p} value={p}>
                {name(p)}
              </option>
            ))}
            <option value="">Not about one seat</option>
          </select>
          <p className="field-hint" id={`${uid}-seathint`}>
            Guessed from the event; change it if the flag is about someone else.
          </p>
        </div>
        <div>
          <label className="field-label" htmlFor={`${uid}-key`}>
            Flag key
          </label>
          <input
            id={`${uid}-key`}
            ref={keyRef}
            className="flag-field"
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={key}
            aria-invalid={keyError ? true : undefined}
            aria-describedby={`${uid}-keyhint${keyError ? ` ${uid}-keyerr` : ""}`}
            onChange={(e) => {
              setKey(e.target.value);
              setKeyError(null);
            }}
          />
          {keyError && (
            <p className="field-error" id={`${uid}-keyerr`}>
              {keyError}
            </p>
          )}
          <p className="field-hint" id={`${uid}-keyhint`}>
            {saved ? "Saved in this browser. " : "Remembered in this browser once a flag is sent. "}
            Sent only with flags.
          </p>
          {saved && (
            <button type="button" className="rail-x flag-forget" onClick={forget}>
              Forget this key
            </button>
          )}
        </div>
      </div>

      <div className="flag-actions">
        <button type="submit" className="btn" aria-busy={sending || undefined}>
          {sending ? "Sending…" : "Send flag"}
        </button>
        <button type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="flag-result" role="status" aria-live="polite">
        {sent && (
          <p>
            <span className="st ok">
              <i />
              Flag sent
            </span>{" "}
            for event <span className="mono">{sent.event}</span>. It is in the review queue, which is
            read every week.
          </p>
        )}
      </div>
      {error && (
        <p className="flag-result" role="alert">
          <span className="st bad">
            <i />
            Not sent
          </span>{" "}
          {error}
        </p>
      )}
    </form>
  );
}
