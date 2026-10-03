import type { ReactNode, SVGProps } from "react";

/** Small inline line-icon set (24px grid, 1.75 stroke, round caps) — no icon dependency needed offline. */
type P = SVGProps<SVGSVGElement> & { size?: number };
const I = ({ size = 18, children, ...p }: P & { children: ReactNode }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round"
    strokeLinejoin="round" aria-hidden focusable="false" className="icon" {...p}>{children}</svg>
);

export const IconGrid = (p: P) => <I {...p}><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></I>;
export const IconPlay = (p: P) => <I {...p}><rect x="3" y="4.5" width="18" height="15" rx="3" /><path d="m10 9 5 3-5 3z" /></I>;
export const IconList = (p: P) => <I {...p}><path d="M9 6h11M9 12h11M9 18h11" /><path d="m3.5 6 1 1 2-2M3.5 12l1 1 2-2M3.5 18l1 1 2-2" /></I>;
export const IconChart = (p: P) => <I {...p}><path d="M4 20V4" /><path d="M4 20h16" /><path d="m7 15 4-5 3 3 5-6" /></I>;
export const IconSettings = (p: P) => <I {...p}><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" /></I>;
export const IconPlus = (p: P) => <I {...p}><path d="M12 5v14M5 12h14" /></I>;
export const IconBack = (p: P) => <I {...p}><path d="m15 18-6-6 6-6" /></I>;
export const IconArrow = (p: P) => <I {...p}><path d="M5 12h14M13 6l6 6-6 6" /></I>;
export const IconSearch = (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></I>;
export const IconSend = (p: P) => <I {...p}><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4z" /></I>;
export const IconChat = (p: P) => <I {...p}><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12z" /></I>;
export const IconClose = (p: P) => <I {...p}><path d="M18 6 6 18M6 6l12 12" /></I>;
export const IconDownload = (p: P) => <I {...p}><path d="M12 4v11M7 10l5 5 5-5" /><path d="M4 20h16" /></I>;
export const IconZoomIn = (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5M11 8v6M8 11h6" /></I>;
export const IconZoomOut = (p: P) => <I {...p}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5M8 11h6" /></I>;
export const IconFit = (p: P) => <I {...p}><path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4" /></I>;
export const IconText = (p: P) => <I {...p}><path d="M4 7V5h16v2M12 5v14M9 19h6" /></I>;
export const IconMic = (p: P) => <I {...p}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></I>;
export const IconWave = (p: P) => <I {...p}><path d="M3 12h2M7 8v8M11 5v14M15 9v6M19 7v10M21 12h0" /></I>;
export const IconFolder = (p: P) => <I {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></I>;
export const IconSpark = (p: P) => <I {...p}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></I>;
export const IconHistory = (p: P) => <I {...p}><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></I>;
export const IconTrash = (p: P) => <I {...p}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></I>;
export const IconInfo = (p: P) => <I {...p}><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8h.01" /></I>;
export const IconCheck = (p: P) => <I {...p}><path d="m5 12 5 5L20 7" /></I>;
export const IconEye = (p: P) => <I {...p}><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></I>;
export const IconCopy = (p: P) => <I {...p}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></I>;
export const IconSliders = (p: P) => <I {...p}><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="10" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></I>;
export const IconStar = ({ filled, ...p }: P & { filled?: boolean }) => <I {...p} fill={filled ? "currentColor" : "none"}><path d="m12 3.5 2.6 5.3 5.9.9-4.2 4.1 1 5.8L12 16.9l-5.3 2.7 1-5.8-4.2-4.1 5.9-.9z" /></I>;
export const IconLink = (p: P) => <I {...p}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></I>;
export const IconUpload = (p: P) => <I {...p}><path d="M12 20V9M7 14l5-5 5 5" /><path d="M4 4h16" /></I>;
