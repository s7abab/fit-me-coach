import type { Metadata, Viewport } from "next";
import { Geist } from "next/font/google";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-body" });

export const metadata: Metadata = {
  title: "Fit Me Coach",
  description: "Training log: sleep, recovery and activity, with a coach that cites its sources.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0f0f0e" },
    { media: "(prefers-color-scheme: light)", color: "#f6f5f2" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={geist.variable}>
      <body>{children}</body>
    </html>
  );
}
