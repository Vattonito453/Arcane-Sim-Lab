/** Brand mascot (DESIGN_SYSTEM.md §6 / spec §2.2): brass artifact robot holding
 *  a fan of three cards, cyan visor, dashed arcane aura. Ships as inline SVG so
 *  the gradients stay crisp at any density — never a raster export. */
export function Mascot({ size = 200 }: { size?: number }) {
  return (
    <svg
      className="masthead-robot-mascot"
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 120 120"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="brassMetallic" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#F59E0B" />
          <stop offset="50%" stopColor="#D97706" />
          <stop offset="100%" stopColor="#78350F" />
        </linearGradient>
        <radialGradient id="arcaneCyanGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#00E5FF" stopOpacity="1" />
          <stop offset="70%" stopColor="#00E5FF" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#00E5FF" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="60" cy="45" r="38" fill="url(#arcaneCyanGlow)" opacity="0.6" />
      <circle cx="60" cy="45" r="28" stroke="#00E5FF" strokeWidth="1.5" strokeDasharray="3,3" fill="none" opacity="0.8" />
      <rect x="36" y="22" width="48" height="42" rx="14" fill="url(#brassMetallic)" stroke="#FDE68A" strokeWidth="2" />
      <circle cx="32" cy="43" r="5" fill="#D97706" stroke="#78350F" strokeWidth="1.5" />
      <circle cx="88" cy="43" r="5" fill="#D97706" stroke="#78350F" strokeWidth="1.5" />
      <rect x="42" y="32" width="36" height="16" rx="8" fill="#0D0F12" stroke="#00E5FF" strokeWidth="1" />
      <ellipse cx="50" cy="40" rx="4" ry="5" fill="#00E5FF" />
      <ellipse cx="70" cy="40" rx="4" ry="5" fill="#00E5FF" />
      <circle cx="51" cy="38" r="1.5" fill="#FFFFFF" />
      <circle cx="71" cy="38" r="1.5" fill="#FFFFFF" />
      <path d="M 48 54 Q 60 62 72 54" stroke="#F59E0B" strokeWidth="2.5" fill="none" strokeLinecap="round" />
      <path d="M 40 68 L 80 68 L 76 92 L 44 92 Z" fill="url(#brassMetallic)" stroke="#78350F" strokeWidth="1.5" />
      <circle cx="60" cy="80" r="6" fill="#00E5FF" opacity="0.9" />
      <rect x="42" y="70" width="12" height="18" rx="2" fill="#1E293B" stroke="#00E5FF" strokeWidth="1" transform="rotate(-20 48 79)" />
      <rect x="54" y="67" width="12" height="18" rx="2" fill="#1E293B" stroke="#A855F7" strokeWidth="1" />
      <rect x="66" y="70" width="12" height="18" rx="2" fill="#1E293B" stroke="#EF4444" strokeWidth="1" transform="rotate(20 72 79)" />
      <circle cx="42" cy="82" r="4" fill="#D97706" />
      <circle cx="78" cy="82" r="4" fill="#D97706" />
    </svg>
  );
}
