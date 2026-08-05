"use client";

import { useState } from "react";

/** The generated SQL, folded away behind a link until asked for. */
export default function SQLDisplay({ sql }: { sql?: string }) {
  const [open, setOpen] = useState(false);
  if (!sql) return null;
  return (
    <div>
      <button
        className="link-btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        {open ? "Hide the SQL" : "View the SQL"}
      </button>
      {open && (
        <pre className="sql-block">
          <code>{sql}</code>
        </pre>
      )}
    </div>
  );
}
