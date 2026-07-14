"use client";

export default function SQLDisplay({ sql }: { sql?: string }) {
  if (!sql) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 12, opacity: 0.6, marginBottom: 4 }}>
        GENERATED SQL
      </div>
      <pre
        style={{
          background: "#1a1d24",
          border: "1px solid #2a2f3a",
          borderRadius: 8,
          padding: 12,
          overflowX: "auto",
          fontSize: 13,
          color: "#9cdcfe",
          fontFamily: "var(--font-datatype), ui-monospace, monospace",
        }}
      >
        {sql}
      </pre>
    </div>
  );
}
