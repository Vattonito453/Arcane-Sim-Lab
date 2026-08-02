"use client";

import { useEffect, useState } from "react";
import { apiBase, setApiBase } from "@/lib/api";

const DEFAULT_BASE = "http://127.0.0.1:8484";

/** Quiet inline control for the engine base URL:
 *  "Engine: 127.0.0.1:8484 · change" — expands to a small inline input. */
export default function ApiBaseSetting({ onChanged }: { onChanged?: () => void }) {
  const [base, setBase] = useState<string | null>(null); // set after mount to avoid hydration mismatch
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setBase(apiBase());
  }, []);

  if (base === null) return null;

  const host = base.replace(/^https?:\/\//, "");

  const save = () => {
    const v = draft.trim();
    const url = v === "" ? DEFAULT_BASE : /^https?:\/\//.test(v) ? v : `http://${v}`;
    setApiBase(url);
    setBase(apiBase());
    setEditing(false);
    onChanged?.();
  };

  if (editing) {
    return (
      <span className="inp">
        <input
          value={draft}
          placeholder={DEFAULT_BASE}
          autoFocus
          spellCheck={false}
          aria-label="Engine base URL"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") setEditing(false);
          }}
        />
        <a
          className="bl"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            save();
          }}
        >
          Save
        </a>
        <a
          className="q"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setEditing(false);
          }}
        >
          Cancel
        </a>
      </span>
    );
  }

  return (
    <span className="ctanote eng">
      <span>
        Engine <span className="mono">{host}</span>
      </span>
      {/* Was an <a href="#"> reading "· change" — a link that goes nowhere, with
          the separator inside its own label, which wrapped to a line of its
          own in the nav sheet. It opens an editor, so it is a button. */}
      <button
        type="button"
        className="rail-x"
        onClick={() => {
          setDraft(base);
          setEditing(true);
        }}
      >
        Change
      </button>
    </span>
  );
}
