"use client";

/** Read-the-card preview — the Moxfield behaviour, in one place.
 *
 *  A 48px row thumbnail and an 84px tabletop card are both far too small to
 *  read, so anywhere a card appears small it gets a full-size face on demand.
 *
 *  Input parity is the whole design (see .claude/skills/ui-review):
 *    mouse     hover the card
 *    keyboard  focus the card (Escape dismisses)
 *    touch     tap where tap is free (/decks); press-and-hold everywhere;
 *              plus an explicit visible control where tap already means
 *              something else (/playtest, where tap plays or taps a card)
 *
 *  The layer is portaled to <body> because our glass panels carry
 *  backdrop-filter, and a filtered ancestor captures position:fixed — an
 *  overlay inside one anchors to the document and scrolls out of view.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { normalizeName, type CardFacts, type CardMap } from "@/lib/cards";

/** Full-size face. cardFace() deliberately downgrades to Scryfall's `small`
 *  render for tiles; reading the card needs `normal`. */
function fullFace(f?: CardFacts): string | null {
  return f?.normal ?? null;
}

const W = 300;              // preview width in CSS px; 5:7 -> 420 tall
const H = Math.round((W * 7) / 5);
const GAP = 14;

interface Shown {
  name: string;
  x: number;
  y: number;
  /** Centred sheet on small screens, anchored card beside the trigger on big. */
  centred: boolean;
}

export function useCardPreview(facts: CardMap) {
  const [shown, setShown] = useState<Shown | null>(null);
  const holdTimer = useRef<number | null>(null);
  const holdFired = useRef(false);
  /** Which input produced the last press — a keyboard-triggered click reports
   *  no pointer at all, so this starts empty rather than assuming "mouse". */
  const lastPointer = useRef<string>("");
  /** The element the open preview is anchored to, kept so a focus-opened
   *  preview can be re-anchored when the page scrolls. */
  const trigger = useRef<{ el: HTMLElement; name: string; fromFocus: boolean } | null>(null);

  const hide = useCallback(() => {
    if (holdTimer.current != null) {
      window.clearTimeout(holdTimer.current);
      holdTimer.current = null;
    }
    trigger.current = null;
    setShown(null);
  }, []);

  /** Anchor beside the trigger, flipping and clamping so the whole card is on
   *  screen.
   *
   *  Two anchor modes, because "beside" only means something for a small
   *  trigger. A tabletop card is 84px wide, so beside it is a real place. A
   *  deck-list row spans the whole panel — measured 1150px of a 1280px
   *  viewport — so both sides overflow, the clamp drops the card at x=8, and
   *  it lands on top of the very row you are reading. For a trigger that wide
   *  we anchor to the pointer instead, offset far enough that the card never
   *  covers the cursor. Position is taken once, on enter, so the card does not
   *  chase the mouse. */
  const showFor = useCallback((name: string, el: HTMLElement, at?: { x: number; y: number }) => {
    trigger.current = { el, name, fromFocus: at == null };
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth || document.documentElement.clientWidth;
    const vh = window.innerHeight || document.documentElement.clientHeight;
    // Below ~560px there is no room beside anything: centre it instead.
    if (vw < 560) {
      setShown({ name, x: 0, y: 0, centred: true });
      return;
    }
    const wide = r.width > W * 1.5;
    let x: number;
    let y: number;
    if (wide && at) {
      x = at.x + GAP * 2;
      if (x + W > vw - 8) x = at.x - W - GAP * 2;   // flip to the cursor's left
      y = at.y - H / 2;
    } else if (wide) {
      // Keyboard focus on a full-width row: no pointer to work from, so park
      // it at the right margin, clear of the name and text on the left.
      x = vw - W - 8;
      y = r.top;
    } else {
      x = r.right + GAP;
      if (x + W > vw - 8) x = r.left - W - GAP;     // flip to the other side
      y = r.top;
    }
    x = Math.max(8, Math.min(x, vw - W - 8));       // clamp inside the viewport
    y = Math.max(8, Math.min(y, vh - H - 8));
    setShown({ name, x, y, centred: false });
  }, []);

  // Escape closes. A resize invalidates every measurement, so dismiss.
  //
  // Scroll is the interesting one. A pointer-opened preview should go away —
  // you scrolled, you are done with it, and the anchor is stale. But tabbing to
  // a card calls scrollIntoView, so a focus-opened preview was being dismissed
  // by the very scroll that revealed its card: measured on /playtest at 375px,
  // focus() opened the sheet and the scroll killed it in the same frame. Those
  // re-anchor to their trigger instead.
  useEffect(() => {
    if (!shown) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") hide();
    };
    const onScroll = () => {
      const t = trigger.current;
      if (t?.fromFocus && t.el.isConnected) showFor(t.name, t.el);
      else hide();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { passive: true, capture: true });
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, { capture: true } as EventListenerOptions);
      window.removeEventListener("resize", hide);
    };
  }, [shown, hide, showFor]);

  /** Handlers to spread onto a card element.
   *  `tap` — let a plain tap/click open the preview. Only pass this where the
   *  element has no other click action, or the two will fight (ui-review §2). */
  const bind = useCallback(
    (name: string, opts: { tap?: boolean } = {}) => ({
      onPointerEnter: (e: React.PointerEvent<HTMLElement>) => {
        if (e.pointerType === "mouse") {
          showFor(name, e.currentTarget, { x: e.clientX, y: e.clientY });
        }
      },
      onPointerLeave: (e: React.PointerEvent<HTMLElement>) => {
        if (e.pointerType === "mouse") hide();
      },
      onFocus: (e: React.FocusEvent<HTMLElement>) => showFor(name, e.currentTarget),
      onBlur: hide,
      // Press-and-hold: works on touch without stealing tap. 400ms is long
      // enough not to fire on a normal tap, short enough not to feel broken.
      onPointerDown: (e: React.PointerEvent<HTMLElement>) => {
        lastPointer.current = e.pointerType;
        if (e.pointerType === "mouse") return;
        holdFired.current = false;
        const el = e.currentTarget;
        const at = { x: e.clientX, y: e.clientY };
        holdTimer.current = window.setTimeout(() => {
          holdFired.current = true;
          showFor(name, el, at);
        }, 400);
      },
      onPointerUp: () => {
        if (holdTimer.current != null) {
          window.clearTimeout(holdTimer.current);
          holdTimer.current = null;
        }
      },
      // A finger that moves is a drag or a scroll, not a hold.
      onPointerMove: () => {
        if (holdTimer.current != null) {
          window.clearTimeout(holdTimer.current);
          holdTimer.current = null;
        }
      },
      // The key is OMITTED, not set to undefined, when tap is not ours: these
      // handlers get spread onto elements that already have their own onClick
      // (a playtest card taps), and a spread `onClick: undefined` coming last
      // silently overwrites it.
      ...(opts.tap
        ? {
            onClick: (e: React.MouseEvent<HTMLElement>) => {
              // Swallow the click that ends a long-press so it does not toggle
              // the preview straight back off.
              if (holdFired.current) {
                holdFired.current = false;
                return;
              }
              // A mouse already previews on hover; letting its click toggle
              // would blank the card out from under a stationary cursor.
              if (lastPointer.current === "mouse") return;
              if (shown?.name === name) hide();
              else showFor(name, e.currentTarget, { x: e.clientX, y: e.clientY });
            },
          }
        : {}),
    }),
    [showFor, hide, shown],
  );

  /** Open explicitly — for a dedicated control (the touch magnifier). */
  const open = useCallback(
    (name: string, el: HTMLElement) => {
      if (shown?.name === name) hide();
      else showFor(name, el);
    },
    [shown, showFor, hide],
  );

  const layer = shown ? <PreviewLayer shown={shown} facts={facts} onClose={hide} /> : null;

  return { bind, open, layer, hide, shownName: shown?.name ?? null };
}

function PreviewLayer({
  shown, facts, onClose,
}: {
  shown: Shown;
  facts: CardMap;
  onClose: () => void;
}) {
  const f = facts[normalizeName(shown.name).toLowerCase()];
  const src = fullFace(f);

  const body = (
    <>
      {/* Centred mode gets a scrim: on a phone the card covers most of the
          screen, so there has to be an obvious way back out. */}
      {shown.centred && <div className="cardpv-scrim" onClick={onClose} />}
      <div
        className={`cardpv${shown.centred ? " cardpv--centred" : ""}`}
        style={shown.centred ? undefined : { left: shown.x, top: shown.y }}
        role="dialog"
        aria-label={
          src ? `${shown.name} — card image` : `${shown.name} — no card image available`
        }
        onClick={shown.centred ? onClose : undefined}
      >
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element -- Scryfall hotlink, never rehosted
          <img src={src} alt={shown.name} />
        ) : (
          // No cached face: say what we know rather than showing a blank card.
          <div className="glass-panel cardpv-text">
            <div className="cardpv-nm">{shown.name}</div>
            <div className="cardpv-tl">
              {f?.type_line ?? "not in the card cache yet — no image available"}
            </div>
            {f?.oracle_text && <div className="cardpv-or">{f.oracle_text}</div>}
          </div>
        )}
      </div>
    </>
  );

  return createPortal(body, document.body);
}
