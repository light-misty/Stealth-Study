import type { ReactNode } from "react";

// 备考台原型的图标集。几何逐字取自 ui-mocks/stealth-study-redesign/index.html 的 sprite，
// 与 Icon.tsx 共用同一套 24 格 / 1.7 描边 / currentColor 语言；独立成表是为了让 Icon.tsx 的
// switch 不再继续膨胀，站点新增图标时只改这一处。

const P = (d: string) => <path d={d} />;

export const campusIcons = {
  check: <polyline points="4.5 12.6 9.4 17.5 19.5 6.8" />,
  minus: <line x1="5" y1="12" x2="19" y2="12" />,
  list: (
    <>
      <line x1="8.6" y1="6" x2="20.5" y2="6" />
      <line x1="8.6" y1="12" x2="20.5" y2="12" />
      <line x1="8.6" y1="18" x2="20.5" y2="18" />
      <circle cx="4.3" cy="6" r="1.2" />
      <circle cx="4.3" cy="12" r="1.2" />
      <circle cx="4.3" cy="18" r="1.2" />
    </>
  ),
  activity: <polyline points="21.5 12.5 17.5 12.5 14.5 20 9 4 6 12.5 2.5 12.5" />,
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2.5" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="8" y1="2.6" x2="8" y2="6.4" />
      <line x1="16" y1="2.6" x2="16" y2="6.4" />
    </>
  ),
  chart: (
    <>
      <line x1="3.5" y1="20.5" x2="20.5" y2="20.5" />
      <rect x="6.4" y="11.4" width="3.6" height="9" rx="1.5" />
      <rect x="14" y="4.6" width="3.6" height="15.8" rx="1.5" />
    </>
  ),
  flame: P(
    "M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z",
  ),
  eye: (
    <>
      <path d="M1.9 12S5.7 5.6 12 5.6 22.1 12 22.1 12 18.3 18.4 12 18.4 1.9 12 1.9 12z" />
      <circle cx="12" cy="12" r="3.1" />
    </>
  ),
  lock: (
    <>
      <rect x="4.6" y="10.4" width="14.8" height="10.4" rx="2.6" />
      {P("M8.2 10.4V7.6a3.8 3.8 0 0 1 7.6 0v2.8")}
    </>
  ),
  pause: (
    <>
      <rect x="7.4" y="4.6" width="3.4" height="14.8" rx="1.6" />
      <rect x="13.2" y="4.6" width="3.4" height="14.8" rx="1.6" />
    </>
  ),
  play: <polygon points="7.4 4.6 19.4 12 7.4 19.4" />,
  forward: (
    <>
      <polygon points="4.4 5.6 12.4 12 4.4 18.4" />
      <line x1="17.4" y1="5" x2="17.4" y2="19" />
    </>
  ),
  upload: (
    <>
      {P("M20.5 15.4v4a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2v-4")}
      <polyline points="7 8.6 12 3.6 17 8.6" />
      <line x1="12" y1="3.6" x2="12" y2="15.2" />
    </>
  ),
  tree: (
    <>
      <rect x="9.4" y="2.6" width="5.2" height="4.6" rx="1.6" />
      <rect x="2.6" y="16.8" width="5.2" height="4.6" rx="1.6" />
      <rect x="16.2" y="16.8" width="5.2" height="4.6" rx="1.6" />
      {P("M12 7.2v4.2M5.2 16.8v-2.6h13.6v2.6")}
    </>
  ),
  bell: (
    <>
      {P("M18 8.6a6 6 0 0 0-12 0c0 6.9-3 8.4-3 8.4h18s-3-1.5-3-8.4")}
      {P("M13.7 20.4a2 2 0 0 1-3.4 0")}
    </>
  ),
  user: (
    <>
      {P("M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2")}
      <circle cx="12" cy="7.5" r="4" />
    </>
  ),
  flag: (
    <>
      <line x1="5.5" y1="21.5" x2="5.5" y2="3.5" />
      {P("M5.5 4.2h12.6l-2.5 4 2.5 4H5.5z")}
    </>
  ),
  sound: (
    <>
      <polygon points="4 9.2 8.6 9.2 13.4 5 13.4 19 8.6 14.8 4 14.8" />
      {P("M16.8 8.6a5 5 0 0 1 0 6.8")}
      {P("M19.4 6a8.6 8.6 0 0 1 0 12")}
    </>
  ),
  timer: (
    <>
      <circle cx="12" cy="13.8" r="7.8" />
      <polyline points="12 13.8 12 9.2" />
      <line x1="9.2" y1="2.6" x2="14.8" y2="2.6" />
      <line x1="12" y1="2.6" x2="12" y2="6" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="9" />
      <line x1="3" y1="12" x2="21" y2="12" />
      {P("M12 3c2.6 2.4 4 5.6 4 9s-1.4 6.6-4 9c-2.6-2.4-4-5.6-4-9s1.4-6.6 4-9z")}
    </>
  ),
} satisfies Record<string, ReactNode>;

export type CampusIconName = keyof typeof campusIcons;
