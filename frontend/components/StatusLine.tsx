"use client";

import { useEffect, useState } from "react";
import { Phase, shuffle, verbsFor } from "../lib/verbs";

const VERB_MS = 4500; // let each verb linger a beat

/**
 * The working indicator: three pulsing dots plus a rotating verb.
 * `className` picks the placement — `status-line` on the home screen,
 * `thinking` in the results body.
 */
export default function StatusLine({
  busy,
  phase,
  className = "status-line",
}: {
  busy: boolean;
  phase: Phase;
  className?: string;
}) {
  const [verb, setVerb] = useState("");

  useEffect(() => {
    if (!busy) return;
    let order = shuffle(verbsFor(phase));
    let i = 0;
    setVerb(order[0]);
    const verbTimer = setInterval(() => {
      i += 1;
      if (i >= order.length) {
        order = shuffle(verbsFor(phase));
        i = 0;
      }
      setVerb(order[i]);
    }, VERB_MS);
    return () => clearInterval(verbTimer);
  }, [busy, phase]);

  if (!busy) return null;

  return (
    <div className={className} role="status" aria-live="polite">
      <span className="dots" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      {verb}…
    </div>
  );
}
