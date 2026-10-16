import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OrgBridge AI — M&A War Room",
  description: "FalkorDB Powered M&A Chaos Resolver (Track 03: Company Brain)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-950 text-slate-100 antialiased h-screen w-screen overflow-hidden">
        {children}
      </body>
    </html>
  );
}
