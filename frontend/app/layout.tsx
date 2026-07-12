export const metadata = {
  title: "LinguaQL",
  description: "ChatGPT for your database",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
          background: "#0f1115",
          color: "#e6e8eb",
        }}
      >
        {children}
      </body>
    </html>
  );
}
