import { createContext, useContext, useEffect, useState } from "react";

// Madison Group Enterprises' palette, taken from their public website, for an
// application demo that is not affiliated with them (the sidebar says so).
//
//   navy   #2E3C49   chrome: sidebar, hero tiles, primary buttons
//   slate  #445B6D   the logo's grey; links and interactive controls
//   red    #E31837   the logo's red; brand accents - active nav, card rules,
//                    the "held" series. Never the only signal of a status:
//                    badges always carry their label.
//   violet #5847C9   anything the triage agent produced, so "the model said
//                    this" is never confused with "the data says this"

export const light = {
  name: "light",
  bg: "#F3F4F5",
  surface: "#FFFFFF",
  surfaceRaised: "#F8F8F8",
  border: "rgba(46,60,73,0.13)",
  borderBright: "rgba(46,60,73,0.28)",
  accent: "#445B6D",
  accentText: "#FFFFFF",
  accentGlow: "rgba(68,91,109,0.10)",
  accent2: "#5847C9",
  accent2Glow: "rgba(88,71,201,0.10)",
  text: "#1E2830",
  textMuted: "rgba(30,40,48,0.66)",
  textDim: "rgba(30,40,48,0.34)",

  sidebarBg: "#2E3C49",
  sidebarText: "rgba(255,255,255,0.78)",
  sidebarActive: "rgba(227,24,55,0.22)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(255,255,255,0.10)",
  sidebarMark: "#E31837",
  sidebarMuted: "rgba(255,255,255,0.58)",
  sidebarGroup: "rgba(255,255,255,0.45)",

  headerBg: "#FFFFFF",
  headerText: "#1E2830",
  headerMuted: "rgba(30,40,48,0.62)",
  headerBorder: "rgba(46,60,73,0.12)",
  headerAccent: "#E31837",

  ctaBg: "#2E3C49",
  ctaText: "#FFFFFF",
  ctaHoverBg: "#E31837",
  ctaHoverText: "#FFFFFF",

  cardRule: "#E31837",
  tableHead: "#EEF0F2",
  statHeroBg: "#2E3C49",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.72)",
  rowHover: "rgba(46,60,73,0.04)",
  rowDivider: "rgba(46,60,73,0.08)",
  grid: "rgba(46,60,73,0.09)",
  code: "rgba(46,60,73,0.06)",
  series: ["#445B6D", "#E31837", "#909DAB", "#2E9A96"],
  status: { good: "#1F7A5A", warning: "#8A6410", serious: "#B4562A", critical: "#B0122B", neutral: "#5B6470", ai: "#5847C9" },
  statusBg: {
    good: "rgba(31,122,90,0.10)", warning: "rgba(227,162,59,0.20)", serious: "rgba(180,86,42,0.12)",
    critical: "rgba(227,24,55,0.09)", neutral: "rgba(46,60,73,0.07)", ai: "rgba(88,71,201,0.10)",
  },
};

export const dark = {
  name: "dark",
  bg: "#141B21",
  surface: "#1C252D",
  surfaceRaised: "#232E38",
  border: "rgba(228,229,230,0.11)",
  borderBright: "rgba(228,229,230,0.24)",
  accent: "#9DB3C6",
  accentText: "#141B21",
  accentGlow: "rgba(157,179,198,0.14)",
  accent2: "#A99BFF",
  accent2Glow: "rgba(169,155,255,0.14)",
  text: "#E8EBEE",
  textMuted: "rgba(232,235,238,0.64)",
  textDim: "rgba(232,235,238,0.32)",

  sidebarBg: "#1F2A34",
  sidebarText: "rgba(232,235,238,0.74)",
  sidebarActive: "rgba(227,24,55,0.24)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(232,235,238,0.08)",
  sidebarMark: "#E31837",
  sidebarMuted: "rgba(232,235,238,0.54)",
  sidebarGroup: "rgba(232,235,238,0.40)",

  headerBg: "#141B21",
  headerText: "#E8EBEE",
  headerMuted: "rgba(232,235,238,0.62)",
  headerBorder: "rgba(232,235,238,0.09)",
  headerAccent: "#FF5C73",

  ctaBg: "#E8EBEE",
  ctaText: "#141B21",
  ctaHoverBg: "#FF5C73",
  ctaHoverText: "#141B21",

  cardRule: "#E31837",
  tableHead: "#232E38",
  statHeroBg: "#E31837",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.80)",
  rowHover: "rgba(232,235,238,0.04)",
  rowDivider: "rgba(232,235,238,0.07)",
  grid: "rgba(232,235,238,0.09)",
  code: "rgba(232,235,238,0.06)",
  series: ["#9DB3C6", "#FF5C73", "#C3CBD3", "#4FC2BD"],
  status: { good: "#5CCB9F", warning: "#E0BE6E", serious: "#F08A5D", critical: "#FF7A8C", neutral: "#A7AEB6", ai: "#A99BFF" },
  statusBg: {
    good: "rgba(92,203,159,0.14)", warning: "rgba(224,190,110,0.16)", serious: "rgba(240,138,93,0.14)",
    critical: "rgba(255,122,140,0.14)", neutral: "rgba(255,255,255,0.08)", ai: "rgba(169,155,255,0.14)",
  },
};

const Ctx = createContext(null);
const KEY = "madison_demo_theme";

function initial() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved === "dark";
  } catch { /* storage blocked */ }
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(initial);
  useEffect(() => {
    try { localStorage.setItem(KEY, isDark ? "dark" : "light"); } catch { /* storage blocked */ }
    document.body.style.background = (isDark ? dark : light).bg;
  }, [isDark]);
  return (
    <Ctx.Provider value={{ t: isDark ? dark : light, isDark, toggle: () => setIsDark((v) => !v) }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme() {
  return useContext(Ctx);
}
