// Tiny inline icon set (stroke icons, currentColor) — no icon library dependency.
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.9, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true, focusable: false };
const I = (children, extra) => (props) => <svg {...base} {...extra} {...props}>{children}</svg>;

export const IconLocate = I(<><circle cx="12" cy="12" r="3.2" /><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" /><circle cx="12" cy="12" r="7.5" /></>);
export const IconLayers = I(<><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 12.5 9 5 9-5" /><path d="m3 16.5 9 5 9-5" opacity=".55" /></>);
export const IconPlus = I(<path d="M12 5v14M5 12h14" />);
export const IconMinus = I(<path d="M5 12h14" />);
export const IconClose = I(<path d="m6 6 12 12M18 6 6 18" />);
export const IconChevronUp = I(<path d="m6 15 6-6 6 6" />);
export const IconChevronDown = I(<path d="m6 9 6 6 6-6" />);
export const IconPin = I(<><path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Z" /><circle cx="12" cy="9.5" r="2.4" /></>);
export const IconRain = I(<><path d="M7 15.5a4.5 4.5 0 1 1 .9-8.9A5.5 5.5 0 0 1 18.5 8a3.8 3.8 0 0 1-.5 7.5H7Z" opacity=".0" /><path d="M12 3.5s5.5 6 5.5 10a5.5 5.5 0 0 1-11 0c0-4 5.5-10 5.5-10Z" /></>);
export const IconDrops = I(<><path d="M8 4s3.5 3.8 3.5 6.4a3.5 3.5 0 0 1-7 0C4.5 7.8 8 4 8 4Z" /><path d="M16.5 11s3 3.2 3 5.4a3 3 0 0 1-6 0c0-2.2 3-5.4 3-5.4Z" /></>);
export const IconWind = I(<><path d="M3 8.5h10.5a2.5 2.5 0 1 0-2.4-3.2" /><path d="M3 12.5h15a2.8 2.8 0 1 1-2.6 3.8" /><path d="M3 16.5h6.5" /></>);
export const IconSun = I(<><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6" /></>);
export const IconInfo = I(<><circle cx="12" cy="12" r="9" /><path d="M12 11v5.2M12 7.7h.01" /></>);
export const IconAlert = I(<><path d="M12 3.5 2.8 19.5h18.4L12 3.5Z" /><path d="M12 10v4.2M12 17.2h.01" /></>);
export const IconLeaf = I(<><path d="M5 19c0-8.5 5-13.5 14.5-14 .3 9.5-4.7 14.5-13 14.5" /><path d="M5 19c2.5-3.5 5.5-6 9-8" /></>);
export const IconTable = I(<><rect x="3.5" y="4.5" width="17" height="15" rx="2.5" /><path d="M3.5 10h17M9.5 10v9.5" /></>);
export const IconCompare = I(<><path d="M7 4v16M17 4v16" /><path d="m3.8 7.2 3.2-3.2 3.2 3.2M13.8 16.8l3.2 3.2 3.2-3.2" /></>);
export const IconRefresh = I(<><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4.5V11h-6.5" /></>);
export const IconLock = I(<><rect x="5" y="10.5" width="14" height="10" rx="2.5" /><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5" /></>);
