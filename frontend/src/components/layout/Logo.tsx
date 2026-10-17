export function LogoMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="8" fill="#4f46e5" />
      <g fill="#fff">
        <rect x="6" y="8" width="9" height="7" rx="1.5" />
        <rect x="17" y="8" width="9" height="7" rx="1.5" opacity=".55" />
        <rect x="6" y="17" width="9" height="7" rx="1.5" opacity=".55" />
        <rect x="17" y="17" width="9" height="7" rx="1.5" />
      </g>
    </svg>
  );
}
