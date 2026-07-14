"use client";

import { useEffect, useState } from "react";
import { Phase, shuffle, verbsFor } from "../lib/verbs";

// Braille spinner frames.
const SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const VERB_MS = 4500; // let each verb linger a beat
const SPIN_MS = 80;

export default function StatusLine({
  busy,
  phase,
  status,
}: {
  busy: boolean;
  phase: Phase;
  status: string;
}) {
  const [verb, setVerb] = useState("");
  const [frame, setFrame] = useState(0);

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
    const spinTimer = setInterval(
      () => setFrame((f) => (f + 1) % SPINNER.length),
      SPIN_MS,
    );
    return () => {
      clearInterval(verbTimer);
      clearInterval(spinTimer);
    };
  }, [busy, phase]);

  if (busy) {
    return (
      <div style={style}>
        <span style={{ opacity: 0.8 }}>{SPINNER[frame]}</span> {verb}…
      </div>
    );
  }
  if (!status) return null;
  return <div style={style}>{status}</div>;
}

const style: React.CSSProperties = {
  marginTop: 12,
  fontSize: 13,
  opacity: 0.75,
  fontFamily: "var(--font-datatype), ui-monospace, monospace",
};
