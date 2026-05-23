import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DevDocs Search — Documentation Search Engine",
  description:
    "Search across Python, MDN, FastAPI, and Kubernetes documentation in one place.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
