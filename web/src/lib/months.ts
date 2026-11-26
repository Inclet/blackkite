/**
 * The app's month words. Short months are always three letters ("17 Sep 2026"):
 * Intl's en-GB short month writes September as "Sept", which reads apart from
 * every other month, so dates are put together from these instead.
 */
export const SHORT_MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;
export const LONG_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'] as const;

/** "17 Sep" from YYYY-MM-DD (a calendar date; no time zone applies). */
export function dayMonth(isoDate: string): string {
  const [, m, d] = isoDate.slice(0, 10).split('-').map(Number);
  return `${d} ${SHORT_MONTHS[m! - 1]}`;
}

/** "17 Sep 2026" from YYYY-MM-DD. */
export function dayMonthYear(isoDate: string): string {
  return `${dayMonth(isoDate)} ${isoDate.slice(0, 4)}`;
}
