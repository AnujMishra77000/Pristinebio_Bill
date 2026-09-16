import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Pristine Bio Billing",
  description: "Billing operations workspace for Pristine Biopharma.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
