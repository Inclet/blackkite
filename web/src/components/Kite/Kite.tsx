import type { CSSProperties } from 'react';
import kiteFullSvg from '@design/assets/kite-full.svg?raw';
import kiteSmallSvg from '@design/assets/kite-small.svg?raw';

function pathData(svg: string): string {
  const d = /\sd="([^"]+)"/.exec(svg)?.[1];
  if (!d) throw new Error('kite svg has no path data');
  return d;
}

/** Path data, read from design/assets (never retyped). */
export const KITE_PATHS = {
  full: pathData(kiteFullSvg),
  small: pathData(kiteSmallSvg),
} as const;

export type KiteVariant = keyof typeof KITE_PATHS;

export interface KiteProps {
  /** full keeps the wingtip feathers (40px wide and above); small below 40px. */
  variant?: KiteVariant;
  width: number;
  height: number;
  /** Rotation in degrees (lockups and app icons use -16). */
  rotate?: number;
  fill?: string;
  /** Accessible name; without it the mark is decorative (aria-hidden). */
  label?: string;
  className?: string;
  style?: CSSProperties;
}

export function Kite({ variant = 'small', width, height, rotate, fill = '#2B2A28', label, className, style }: KiteProps) {
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true as const };
  return (
    <svg
      {...a11y}
      viewBox="0 0 120 80"
      className={className}
      style={{ width, height, ...(rotate !== undefined ? { transform: `rotate(${rotate}deg)` } : {}), ...style }}
    >
      <path d={KITE_PATHS[variant]} fill={fill} />
    </svg>
  );
}
