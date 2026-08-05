import Link from "next/link";

export default function NotFound() {
  return (
    <div className="stage">
      <section className="screen screen-404">
        <span className="brand-mark-sm">
          Lingua<span className="ql">QL</span>
        </span>
        <h2>That page doesn&rsquo;t exist.</h2>
        <p className="text-muted" style={{ maxWidth: "40ch" }}>
          The link may be old, or mistyped. Let&rsquo;s get you back to asking
          questions.
        </p>
        <Link className="btn btn-primary" href="/">
          Back to LinguaQL →
        </Link>
      </section>
    </div>
  );
}
