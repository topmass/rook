// Rook's activity icons: the desktop dust's forms as gold line drawings, the dotted part of each its dust.
// Copied from Rook's phone app (phone/index.html, the svg sprite), MIT License, Copyright (c) 2026 topmass.
import { CSSProperties, ReactNode } from "react";

const D = (props: { d: string; w?: number; dots?: string; fill?: boolean }) => (
  <path
    d={props.d}
    strokeWidth={props.w}
    strokeDasharray={props.dots}
    fill={props.fill ? "currentColor" : undefined}
  />
);

const SHAPES: Record<string, ReactNode> = {
  thinking: (<>
    <D d="M12 3.2 19.6 7.6v8.8L12 20.8 4.4 16.4V7.6Z" /><D d="M4.4 7.6 12 12l7.6-4.4M12 12v8.8" />
    <D d="M8.2 5.4l7.6 4.4M15.8 5.4 8.2 9.8" w={1.7} dots="0 2.6" />
  </>),
  reading: (<>
    <D d="M6.5 3.5H14l4 4v13H6.5Z" /><D d="M14 3.5v4h4" />
    <D d="M9.5 11.5h5.6M9.5 14.5h5.6M9.5 17.5h3" w={1.9} dots="0 2.8" />
  </>),
  searching: (<>
    <circle cx="10.5" cy="10.5" r="6.2" /><D d="m15.2 15.2 5 5" w={2.2} />
    <D d="M7.4 9.6a3.4 3.4 0 0 1 2.2-2.3" w={1.8} dots="0 2.4" />
  </>),
  running: (<>
    <D d="m4.5 6.5 6 5.5-6 5.5" w={2} /><D d="M13 18h7" w={2} dots="0 3.4" />
  </>),
  editing: (<>
    <D d="M20 3.6C13.4 4.2 8.6 9 7.6 16.4 14.2 15.8 19 11 20 3.6Z" /><D d="M4 20.4 15 9.4" />
    <D d="M10.6 21h9" w={1.9} dots="0 3" />
  </>),
  sending: (<>
    <D d="M20.6 3.4c-.6 1.8-6.6 7.8-10.2 10.6 2.8-3.6 8.8-9.6 10.2-10.6Z" />
    <D d="M18.4 5.6C13 2.8 5.2 6.4 7.6 11.2s-1.6 8.4-4.2 9.4" w={1.9} dots="0 2.8" />
  </>),
  launching: (<>
    <D d="M4.5 4.5h10M4.5 15.5h10" w={2.2} /><D d="M6.2 4.5v11M12.8 4.5v11" />
    <D d="M6.6 8h5.8M6.6 10.5h5.8M6.6 13h5.8" w={1.1} />
    <D d="M12.8 9.2c4.6-.4 6.6 2.6 6 6.2-.4 2.4.6 4 1.8 5" w={1.9} dots="0 2.8" />
  </>),
  waiting: (<>
    <D d="M12 3.8a8.2 8.2 0 0 1 8.2 8.2" w={2} />
    <D d="M20.2 12A8.2 8.2 0 1 1 9 4.3" w={1.8} dots="0 3" />
  </>),
  showing: (<>
    <rect x="3.2" y="5" width="17.6" height="14" rx="1.6" />
    <D d="M5.8 7.6h12.4M5.8 16.4h12.4" w={1.6} dots="0 2.5" />
    <D d="M10.6 10.2v3.6l3.2-1.8Z" w={1} fill />
  </>),
  drawing: (<>
    <D d="M7.2 15.8 11 8.2M13.2 8.1l4.3 5.8M16.4 16.1l-8.2 1.3" w={1.8} dots="0 2.6" />
    <circle cx="12" cy="6" r="2" fill="currentColor" /><circle cx="6.2" cy="17.6" r="2" fill="currentColor" />
    <circle cx="18.6" cy="15.6" r="2" fill="currentColor" />
  </>),
  timing: (<>
    <D d="M6.8 3.5h10.4M6.8 20.5h10.4" w={2} />
    <D d="M8.2 3.5c0 4.8 7.6 5.8 7.6 8.5s-7.6 3.7-7.6 8.5M15.8 3.5c0 4.8-7.6 5.8-7.6 8.5s7.6 3.7 7.6 8.5" />
    <D d="M12 12.8v3M10.2 18.6h3.6" w={1.8} dots="0 2.2" />
  </>),
  game: (<>
    <D d="M20.4 3.6 17.6 4.2 9.8 12l2.2 2.2 7.8-7.8Z" /><D d="m7 11.6 5.4 5.4M9.4 15.6l-4.2 4.2" w={2} />
  </>),
  speaking: (<>
    <circle cx="12" cy="12" r="4" /><circle cx="12" cy="12" r="8.4" strokeWidth={1.9} strokeDasharray="0 3.3" />
  </>),
  tool: (<>
    <D d="M18.31 10.43 20.69 10.62 20.69 13.38 18.31 13.57 17.57 15.35 19.12 17.17 17.17 19.12 15.35 17.57 13.57 18.31 13.38 20.69 10.62 20.69 10.43 18.31 8.65 17.57 6.83 19.12 4.88 17.17 6.43 15.35 5.69 13.57 3.31 13.38 3.31 10.62 5.69 10.43 6.43 8.65 4.88 6.83 6.83 4.88 8.65 6.43 10.43 5.69 10.62 3.31 13.38 3.31 13.57 5.69 15.35 6.43 17.17 4.88 19.12 6.83 17.57 8.65Z" />
    <circle cx="12" cy="12" r="2.8" strokeWidth={1.8} strokeDasharray="0 2.2" />
  </>),
  dot: <circle cx="12" cy="12" r="2.6" fill="currentColor" stroke="none" />,
  voice: (<>
    <D d="M4 9.5h3.2L12 5.5v13l-4.8-4H4Z" /><D d="M15.4 9a4.2 4.2 0 0 1 0 6" />
    <D d="M18 6.4a8 8 0 0 1 0 11.2" w={1.9} dots="0 2.8" />
  </>),
  stop: <rect x="7.5" y="7.5" width="9" height="9" rx="1.6" fill="currentColor" stroke="none" />,
  rook: (<>
    <D d="M7 20.5h10M8 17.5h8l-.8-7h-6.4Z" /><D d="M7.2 10.5h9.6V5.5h-2.2v2h-1.6v-2h-2v2H9.4v-2H7.2Z" />
    <D d="M5 20.5h14" w={1.8} dots="0 2.6" />
  </>),
};

export const ICON_NAMES = new Set(Object.keys(SHAPES));

// The icon for an activity line: its own icon name if known, else its kind, else the plain dot.
export function stepIcon(step: { icon?: string; kind?: string }): string {
  if (step.icon) return ICON_NAMES.has(step.icon) ? step.icon : "dot";
  return step.kind && ICON_NAMES.has(step.kind) ? step.kind : "dot";
}

export function Icon({ name, size = 18, style }: { name: string; size?: number; style?: CSSProperties }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flex: "none", color: "var(--rook-gold)", ...style }}
    >
      {SHAPES[name] ?? SHAPES.dot}
    </svg>
  );
}
