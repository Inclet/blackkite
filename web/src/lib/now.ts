/**
 * The single source of "now" for the app. Every date calculation (days to a
 * deadline, greeting, digest week) must call now() rather than new Date() or
 * Date.now(), so tests can freeze it with setNowForTests().
 */
let frozen: number | null = null;

export function now(): Date {
  return new Date(frozen ?? Date.now());
}

/** Freeze the clock (tests only). Pass null to unfreeze. */
export function setNowForTests(at: Date | string | number | null): void {
  frozen = at === null ? null : new Date(at).getTime();
}
