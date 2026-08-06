import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Trade Ledger",
  description: "A simple multi-day trading journal with DCA-aware analytics.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
