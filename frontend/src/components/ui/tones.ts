export type Tone = "slate" | "indigo" | "green" | "amber" | "red" | "blue";

interface ToneClasses {
  /** soft background + text + border (chips, banners) */
  soft: string;
  /** coloured dot / icon colour */
  icon: string;
  /** strong text colour */
  text: string;
  /** solid background (progress, dots) */
  solid: string;
}

export const TONES: Record<Tone, ToneClasses> = {
  slate: {
    soft: "bg-slate-100 text-slate-700 border-slate-200",
    icon: "text-slate-500",
    text: "text-slate-700",
    solid: "bg-slate-500",
  },
  indigo: {
    soft: "bg-indigo-50 text-indigo-700 border-indigo-200",
    icon: "text-indigo-600",
    text: "text-indigo-700",
    solid: "bg-indigo-600",
  },
  green: {
    soft: "bg-emerald-50 text-emerald-800 border-emerald-200",
    icon: "text-emerald-600",
    text: "text-emerald-700",
    solid: "bg-emerald-500",
  },
  amber: {
    soft: "bg-amber-50 text-amber-900 border-amber-200",
    icon: "text-amber-600",
    text: "text-amber-800",
    solid: "bg-amber-500",
  },
  red: {
    soft: "bg-red-50 text-red-800 border-red-200",
    icon: "text-red-600",
    text: "text-red-700",
    solid: "bg-red-500",
  },
  blue: {
    soft: "bg-sky-50 text-sky-800 border-sky-200",
    icon: "text-sky-600",
    text: "text-sky-700",
    solid: "bg-sky-500",
  },
};
