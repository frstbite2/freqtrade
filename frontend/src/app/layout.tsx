import "@fontsource-variable/inter";
import "@fontsource-variable/space-grotesk";
import "./globals.css";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { MobileNav } from "@/components/shell/mobile-nav";
import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { DemoBanner } from "@/components/shell/demo-banner";
import { BRAND } from "@/lib/brand";
import { DataModeProvider } from "@/lib/data-mode";

export const metadata: Metadata = {
  title: { default: `${BRAND.name} · ${BRAND.tagline}`, template: `%s · ${BRAND.name}` },
  description: "AI trading research command centre. Paper trading only.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: "#06050a",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="backdrop" aria-hidden />
        <DataModeProvider>
          <div className="flex min-h-dvh">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Topbar />
              <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 pb-28 pt-6 sm:px-6 lg:px-8 lg:pb-12">
                <DemoBanner />
                {children}
              </main>
            </div>
          </div>
          <MobileNav />
        </DataModeProvider>
      </body>
    </html>
  );
}
