import type { CSSProperties } from 'react';
import icons from '@design/assets/icons.json';

export type StreamIconName = keyof typeof icons.stream;
export type TrustIconName = keyof typeof icons.trust;
export type UiIconName = keyof typeof icons.ui;
export type IconName = StreamIconName | TrustIconName | UiIconName;

interface CircleSpec {
  cx: number;
  cy: number;
  r: number;
  strokeDasharray?: string;
}

interface Shape {
  circle?: CircleSpec;
  path?: string;
  /** Round caps and joins. The board draws the dashed "unconfirmed" circle without them. */
  round: boolean;
}

function shapeOf(name: IconName): Shape {
  if (name in icons.stream) return { path: icons.stream[name as StreamIconName], round: true };
  if (name in icons.trust) {
    const t = icons.trust[name as TrustIconName] as { circle?: CircleSpec; path?: string };
    return { ...t, round: name !== 'unconfirmed' };
  }
  const u = icons.ui[name as UiIconName];
  return typeof u === 'string' ? { path: u, round: true } : { ...u, round: true };
}

export interface IconProps {
  name: IconName;
  /** Rendered width and height, px. */
  size?: number;
  stroke?: string;
  /** 1.4 in tiles and tags, 1.6 on white chips, 1.5 for trust icons. */
  strokeWidth?: number;
  /** Accessible name; without it the icon is decorative. */
  label?: string;
  className?: string;
  style?: CSSProperties;
}

/** Icons from design/assets/icons.json only: viewBox 16, no fill. */
export function Icon({ name, size = 16, stroke = 'currentColor', strokeWidth = 1.5, label, className, style }: IconProps) {
  const { circle, path, round } = shapeOf(name);
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true as const };
  return (
    <svg
      {...a11y}
      viewBox="0 0 16 16"
      className={className}
      // stroke also as a CSS property so var(--bk-*) values resolve.
      style={{ width: size, height: size, stroke, ...style }}
      fill="none"
      stroke={stroke}
      strokeWidth={strokeWidth}
      {...(round ? { strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const } : {})}
      data-icon={name}
    >
      {circle && <circle cx={circle.cx} cy={circle.cy} r={circle.r} strokeDasharray={circle.strokeDasharray} />}
      {path && <path d={path} />}
    </svg>
  );
}
