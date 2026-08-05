"use client";

import { useEffect, useState } from "react";
import SQLDisplay from "./SQLDisplay";
import ChartRenderer from "./ChartRenderer";
import StatusLine from "./StatusLine";
import type { Phase } from "../lib/verbs";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SAMPLE_DB_URL =
  process.env.NEXT_PUBLIC_SAMPLE_DB_URL ||
  "postgresql://demo:demo@sample-db:5432/shop";
const DEV = process.env.NEXT_PUBLIC_DEV_MODE === "true";

const EXAMPLES = [
  "total revenue by month",
  "top 5 products by revenue",
  "average order value by country",
  "best-rated products",
];

function maskDbUrl(url: string): string {
  const m = url.match(/^(\w+:\/\/)([^:@/]+):([^@]+)@([^/]+)(\/.*)?$/);
  if (!m) return url;
  const [, scheme, user, , , path = ""] = m;
  return `${scheme}${user}:****@****${path}`;
}


async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.error === "string") return body.error;
  } catch {
    /* not JSON — fall through */
  }
  return `Request failed (${res.status}).`;
}

export default function ChatInterface() {
  const [screen, setScreen] = useState<"home" | "results">("home");
  const [projectId, setProjectId] = useState<string | null>(null);
  const [dbUrl, setDbUrl] = useState("");
  const [dbFocused, setDbFocused] = useState(false);
  const [connectError, setConnectError] = useState<string | null>(null);
  const [toast, setToast] = useState("");
  const [howto, setHowto] = useState(false);

  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [result, setResult] = useState<any>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [details, setDetails] = useState(false);

  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("query");
  const [remaining, setRemaining] = useState<number | null>(null);
  const [limit, setLimit] = useState<number | null>(null);

  function refreshLimits() {
    fetch(`${API}/limits`)
      .then((r) => r.json())
      .then((d) => {
        setRemaining(d.queries_remaining);
        setLimit(d.queries_limit);
      })
      .catch(() => {});
  }
  // Load the shared daily budget on mount.
  useEffect(refreshLimits, []);

  const outOfBudget = remaining != null && remaining <= 0;
  const connected = projectId != null;

  async function connect(url: string = dbUrl) {
    const target = url.trim();
    if (!target || busy) return;
    setDbUrl(target);
    setBusy(true);
    setPhase("ingest");
    setConnectError(null);
    setToast("");
    try {
      const created = await fetch(`${API}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "demo", db_url: target }),
      });
      if (!created.ok) throw new Error(await readError(created));
      const p = await created.json();

      const reload = await fetch(`${API}/projects/${p.id}/reload`, {
        method: "POST",
      });
      if (!reload.ok) throw new Error(await readError(reload));
      const reloaded = await reload.json();

      setProjectId(p.id);
      setToast(
        `Connected. ${reloaded.table_count} tables, ${reloaded.column_count} columns ingested.`,
      );
    } catch (e: any) {
      setConnectError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function ask(text: string, forceBad = false, confirmed = false) {
    const q = text.trim();
    if (!projectId || !q || outOfBudget || busy) return;
    setScreen("results");
    setAsked(q);
    setQuestion(q);
    setBusy(true);
    setPhase("query");
    setResult(null);
    setAskError(null);
    setDetails(false);
    try {
      const res = await fetch(`${API}/projects/${projectId}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          confirmed,
          force_bad_column: forceBad ? "definitely_not_a_column" : null,
        }),
      });
      const r = await res.json();
      if (r.queries_remaining != null) setRemaining(r.queries_remaining);
      if (r.queries_limit != null) setLimit(r.queries_limit);
      // A throttled or over-budget request comes back as a bare error body,
      // without the pipeline fields a real QueryResult carries.
      if (!res.ok && r.generated_sql == null && !r.needs_clarification) {
        setAskError(r.error || r.detail || `Request failed (${res.status}).`);
      } else {
        setResult(r);
        if (r.error) setAskError(r.error);
      }
    } catch (e: any) {
      setAskError(e.message);
    } finally {
      setBusy(false);
    }
  }

  function goHome() {
    setScreen("home");
    setResult(null);
    setAskError(null);
  }

  const cols: string[] = result?.columns || [];
  const rows: any[] = result?.rows || [];
  const hasAnswer = result && result.ok && !result.needs_clarification;
  const budgetTag =
    remaining != null && limit != null
      ? { full: `${remaining} / ${limit} free queries left today`, short: `${remaining} / ${limit} left` }
      : null;

  const dbIcon = (
    <svg
      className="bar-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  );

  return (
    <div className="stage">
      {/* ── Home ─────────────────────────────────────────────────────── */}
      <section className="screen screen-home" hidden={screen !== "home"}>
        <div className="home-topbar">
          <button
            className="link-btn"
            onClick={() => setHowto((h) => !h)}
            aria-expanded={howto}
          >
            How it works
          </button>
          {budgetTag && (
            <span
              className={outOfBudget ? "tag tag-accent" : "tag tag-neutral"}
              title="Shared daily demo budget"
            >
              {budgetTag.full}
            </span>
          )}
        </div>

        <div className="home-center">
          <h1 className="brand-mark">
            Lingua<span className="ql">QL</span>
          </h1>
          <p className="tagline">
            {connected
              ? "Ask a question the way you’d say it out loud."
              : "Speak with your database in plain English."}
          </p>

          <div className="bar-row">
            {dbIcon}
            {connected ? (
              <input
                className="input bar-input"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask(question)}
                placeholder="e.g. total revenue by month"
                aria-label="Your question"
              />
            ) : (
              <input
                className="input bar-input"
                value={dbFocused ? dbUrl : maskDbUrl(dbUrl)}
                onChange={(e) => setDbUrl(e.target.value)}
                onFocus={() => setDbFocused(true)}
                onBlur={() => setDbFocused(false)}
                onKeyDown={(e) => e.key === "Enter" && connect()}
                placeholder="Paste your database connection URL"
                aria-label="Database connection URL"
              />
            )}
            <button
              className="btn btn-primary bar-btn"
              onClick={() => (connected ? ask(question) : connect())}
              disabled={
                busy ||
                (connected ? outOfBudget || !question.trim() : !dbUrl.trim())
              }
            >
              {connected ? "Ask →" : "Connect →"}
            </button>
          </div>

          {!connected && !busy && (
            <div className="bar-help">
              <button className="link-btn" onClick={() => connect(SAMPLE_DB_URL)}>
                Or try the sample store instantly
              </button>
              <span className="reassure">
                Read-only. Nothing is stored — LinguaQL can only ever read your
                data.
              </span>
            </div>
          )}

          <StatusLine busy={busy} phase={phase} />

          {connectError && !busy && (
            <div className="error-inline">
              <strong>We couldn’t reach that database.</strong>
              <p>{connectError}</p>
              <p>
                Check that the URL is correct and that this address allows
                outside connections.
              </p>
              <div className="actions">
                <button
                  className="btn btn-secondary"
                  onClick={() => connect()}
                  disabled={!dbUrl.trim()}
                >
                  Try again
                </button>
                <button
                  className="btn btn-secondary"
                  onClick={() => connect(SAMPLE_DB_URL)}
                >
                  Use the sample database instead
                </button>
              </div>
            </div>
          )}

          {connected && toast && !busy && (
            <div className="toast-line">{toast}</div>
          )}

          {connected && !busy && (
            <div className="chips-row">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  className="chip"
                  onClick={() => ask(ex)}
                  disabled={outOfBudget}
                >
                  {ex}
                </button>
              ))}
            </div>
          )}

          {outOfBudget && (
            <p className="reassure">
              That&rsquo;s a wrap for today 🎬... the daily budget is spent. Come
              back tomorrow!
            </p>
          )}

          {howto && (
            <div className="howto">
              <h3>Lingua 101</h3>
              <ol>
                <li>
                  A sample database is already provided — just click{" "}
                  <b>Or try the sample store instantly</b> to load it.
                </li>
                <li>
                  Prefer your own data? Paste any PostgreSQL / MySQL connection
                  URL in the box above, then <b>Connect</b>.
                </li>
                <li>
                  Ask a question in plain English and hit <b>Ask</b>.
                </li>
              </ol>
              <p className="try-line">
                Try: &ldquo;total revenue by month&rdquo; &middot; &ldquo;top 5
                products by revenue&rdquo; &middot; &ldquo;average order value by
                country&rdquo; &middot; &ldquo;best-rated products&rdquo;
              </p>
            </div>
          )}
        </div>
      </section>

      {/* ── Results ──────────────────────────────────────────────────── */}
      <section className="screen screen-results" hidden={screen !== "results"}>
        <header className="results-header">
          <button
            className="brand-mark-sm brand-link"
            onClick={goHome}
            title="Back to the start"
          >
            Lingua<span className="ql">QL</span>
          </button>
          <div className="bar-row">
            <input
              className="input bar-input"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask(question)}
              placeholder="Ask another question…"
              disabled={outOfBudget}
              aria-label="Your question"
            />
            <button
              className="btn btn-primary bar-btn"
              onClick={() => ask(question)}
              disabled={busy || outOfBudget || !question.trim()}
            >
              Ask
            </button>
          </div>
          {budgetTag && (
            <span
              className={outOfBudget ? "tag tag-accent" : "tag tag-neutral"}
              title="Shared daily demo budget"
            >
              {budgetTag.short}
            </span>
          )}
          {DEV && (
            <button
              className="btn btn-secondary"
              onClick={() => ask(question, true)}
              disabled={busy || outOfBudget || !question.trim()}
              title="Injects a bad column to demonstrate the validator + self-correction loop"
            >
              Force guardrail
            </button>
          )}
        </header>

        <main className="results-body">
          <StatusLine busy={busy} phase={phase} className="thinking" />

          {/* Answer */}
          {!busy && hasAnswer && (
            <div className="panel">
              {result.confidence_score != null && (
                <p className="understanding-line">
                  Answered at {Number(result.confidence_score).toFixed(2)}{" "}
                  confidence · {result.chart_type} · {result.retry_count} retries{" "}
                  <button
                    className="link-btn"
                    onClick={() => setDetails((d) => !d)}
                    aria-expanded={details}
                  >
                    details
                  </button>
                </p>
              )}
              {details && (
                <ul className="assumptions-list">
                  {result.complexity_score != null && (
                    <li>complexity {result.complexity_score}</li>
                  )}
                  {result.explain_cost != null && (
                    <li>est. cost {Number(result.explain_cost).toFixed(0)}</li>
                  )}
                  {(result.validation_errors || []).map(
                    (v: string, i: number) => (
                      <li key={i}>corrected: {v}</li>
                    ),
                  )}
                </ul>
              )}

              <h2>{asked}</h2>

              <ChartRenderer
                chartType={result.chart_type}
                chartData={result.chart_data}
              />

              {cols.length > 0 && (
                <div className="table-scroll">
                  <table className="table">
                    <thead>
                      <tr>
                        {cols.map((c) => (
                          <th key={c}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, i) => (
                        <tr key={i}>
                          {cols.map((c) => (
                            <td key={c}>{String(row[c])}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <SQLDisplay sql={result.generated_sql} />
            </div>
          )}

          {/* Needs clarification */}
          {!busy && result?.needs_clarification && (
            <div className="panel card panel-padded">
              <div className="card-kicker">Which did you mean?</div>
              <p style={{ margin: 0, fontSize: 16 }}>{result.clarification}</p>
              <div>
                <button
                  className="btn btn-primary"
                  onClick={() => ask(asked, false, true)}
                  disabled={busy}
                >
                  Confirm &amp; run
                </button>
              </div>
              <SQLDisplay sql={result.generated_sql} />
            </div>
          )}

          {/* Daily budget spent */}
          {!busy && outOfBudget && (
            <div className="panel card panel-padded">
              <div className="card-kicker">Today&rsquo;s free questions are used up</div>
              <p style={{ margin: 0, fontSize: 16 }}>
                That&rsquo;s a wrap for today 🎬... the daily budget is spent.
                Come back tomorrow!
              </p>
              <div>
                <button className="btn btn-secondary" onClick={goHome}>
                  Back to the start
                </button>
              </div>
            </div>
          )}

          {/* Something went wrong */}
          {!busy && askError && !outOfBudget && (
            <div className="panel card panel-padded">
              <p style={{ margin: 0, fontSize: 16 }}>{askError}</p>
              {result?.needs_reload && (
                <p className="text-muted" style={{ margin: 0 }}>
                  The schema looks out of date — reconnect from the start screen
                  to reload it.
                </p>
              )}
              <div>
                <button
                  className="btn btn-secondary"
                  onClick={() => ask(asked)}
                  disabled={busy || !asked}
                >
                  Try again
                </button>
              </div>
            </div>
          )}
        </main>
      </section>
    </div>
  );
}
