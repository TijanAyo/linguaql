import "./globals.css";

export const metadata = {
  title: "LinguaQL",
  description: "Ask your database in plain English",
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
