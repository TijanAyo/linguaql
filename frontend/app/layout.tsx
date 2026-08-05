import "./globals.css";

export const metadata = {
  title: "LinguaQL",
  description: "Speak with your database in plain English",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

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
        {/* Archivo carries the UI; Datatype stays for SQL and tabular figures. */}
        <link
          href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;600;800&family=Datatype:wght@100..900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
