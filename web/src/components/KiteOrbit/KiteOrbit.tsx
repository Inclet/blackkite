import type { CSSProperties, ReactNode } from 'react';
import { Kite } from '../Kite/Kite';
import styles from './KiteOrbit.module.css';

export interface OrbitSpec {
  /** Outer size in px. */
  size: number;
  /** Inset of each ring from the outer edge, px. */
  rings: number[];
  ringColor: string;
  /** One full circle, e.g. "8s". */
  duration: string;
  /** Kite box inside the rotating layer, px. */
  kite: { left: number; top: number; width: number; height: number };
}

/** The three orbits drawn on the boards. */
export const ORBITS = {
  /** Foundations board, signature demo (board-only motion, decision 9). */
  signature: { size: 150, rings: [0, 28, 56], ringColor: 'var(--bk-stone-200)', duration: '14s', kite: { left: 54, top: -14, width: 42, height: 28 } },
  /** Components board, "State · checking". */
  checking: { size: 72, rings: [0, 22], ringColor: 'var(--bk-stone-200)', duration: '6s', kite: { left: 21, top: -10, width: 30, height: 20 } },
  /** Feed header, beside "8 sources checked this morning". */
  feed: { size: 28, rings: [0], ringColor: 'var(--bk-stone-300)', duration: 'var(--bk-orbit)', kite: { left: 5, top: -6, width: 18, height: 12 } },
} satisfies Record<string, OrbitSpec>;

export interface KiteOrbitProps {
  orbit?: OrbitSpec;
  className?: string;
  /** Extra absolutely-positioned marks inside the orbit (the board's stream dots). */
  children?: ReactNode;
}

/** The circling kite. It replaces every spinner. */
export function KiteOrbit({ orbit = ORBITS.feed, className, children }: KiteOrbitProps) {
  const { size, rings, ringColor, duration, kite } = orbit;
  return (
    <div className={[styles.orbit, className].filter(Boolean).join(' ')} style={{ width: size, height: size }} data-testid="kite-orbit">
      {rings.map((inset) => (
        <div key={inset} className={styles.ring} style={{ inset, borderColor: ringColor }} />
      ))}
      {children}
      <div className={styles.spin} style={{ animationDuration: duration } as CSSProperties}>
        <Kite
          width={kite.width}
          height={kite.height}
          rotate={90}
          style={{ position: 'absolute', left: kite.left, top: kite.top }}
        />
      </div>
    </div>
  );
}
