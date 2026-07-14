import "./globals.css";

export const metadata = {
  title: "LinguaQL",
  description: "ChatGPT for your database",
};

// Datatype (Google Fonts) — variable monospace, weight axis 100–900, width
// baked at 100. Loaded via <link> for compatibility across Next font-data
// versions; used app-wide via `--font-datatype` (see globals.css). Gracefully
// falls back to the system monospace stack if the request ever fails.
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Datatype:wght@100..900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body
        style={{
          margin: 0,
          background: "#0f1115",
          color: "#e6e8eb",
        }}
      >
        {children}
      </body>
    </html>
  );
}
