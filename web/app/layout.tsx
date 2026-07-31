import type { Metadata } from "next";
import { Cinzel, Space_Grotesk, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const cinzel = Cinzel({ subsets: ["latin"], weight: ["700"], variable: "--font-cinzel" });
const grotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-grotesk" });
const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jbmono" });

export const metadata: Metadata = {
  title: "Arcane Sim Lab",
  description: "Commander deck testing lab — simulate, replay, coach.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Font variables live on <html>: the token sheet's :root rules reference
    // them (--font-ui: var(--font-grotesk), …), and custom properties resolve
    // against the element they're declared on — on <body> they'd be invisible
    // to :root and every font token would compute to invalid.
    <html lang="en" className={`${cinzel.variable} ${grotesk.variable} ${jbMono.variable}`}>
      <body>
        {/* Backdrop stack (DESIGN_SYSTEM.md §11): atmosphere under the art so a
            failed load reads as sky, then the plate, then scrim + vignette via
            the .backdrop pseudo-elements. Fixed so the scene holds still. */}
        <div className="backdrop backdrop--app" aria-hidden="true">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="backdrop__art" src="/art/backdrop-hedron-ruins.png" alt="" />
        </div>
        <div className="app-content">{children}</div>
      </body>
    </html>
  );
}
