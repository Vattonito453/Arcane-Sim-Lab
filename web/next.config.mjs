/** Engine origin the /engine/* proxy forwards to. Only used by the rewrite
 *  below, so it is a server-side value and never reaches the browser bundle. */
const ENGINE_ORIGIN = process.env.ENGINE_ORIGIN || "http://127.0.0.1:8484";

/** @type {import('next').NextConfig} */
const nextConfig = {
  /** Build output directory.
   *
   *  `next build` writes into the same place `next dev` is serving from, so a
   *  verification build run against a live dev server pulls the rug out from
   *  under it: the page dies with "Cannot find module './941.js'" and stays dead
   *  until dev is restarted. Setting NEXT_DIST_DIR sends a build somewhere else,
   *  which is what `npm run verify` does. Unset everywhere else, so dev, `npm
   *  run build` and `npm start` all keep using .next as before.
   */
  distDir: process.env.NEXT_DIST_DIR || ".next",
  images: {
    remotePatterns: [{ protocol: "https", hostname: "api.scryfall.com" }],
  },
  /** Same-origin path to the engine.
   *
   *  Hosting this for remote playtesters means the browser is no longer on the
   *  same machine as the engine, and the default http://127.0.0.1:8484 base
   *  resolves to the *visitor's* laptop. Pointing NEXT_PUBLIC_API_BASE at
   *  /engine instead routes every call through this app's own origin, which
   *  removes the second public hostname, the CORS configuration, and the
   *  mixed-content problem an https page calling http://… would otherwise hit.
   *  Unset in local dev, where talking straight to 127.0.0.1:8484 is fine.
   */
  async rewrites() {
    return [{ source: "/engine/:path*", destination: `${ENGINE_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
