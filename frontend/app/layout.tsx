import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Neural Bridge",
  description: "BCI simulation ecosystem and interactive prototype"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
