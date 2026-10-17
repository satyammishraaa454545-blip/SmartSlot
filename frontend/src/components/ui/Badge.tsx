import type { HTMLAttributes, ReactNode } from "react";
import { TONES, type Tone } from "./tones";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  icon?: ReactNode;
  size?: "sm" | "md";
}

export function Badge({ tone = "slate", icon, size = "md", className = "", children, ...rest }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border font-semibold ${
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs"
      } ${TONES[tone].soft} ${className}`}
      {...rest}
    >
      {icon}
      {children}
    </span>
  );
}
