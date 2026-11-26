import { describe, expect, it } from 'vitest';
import { formatShortDate } from './deadline';
import { formatFullDate, formatWhen } from './detailWords';
import { dayMonth, dayMonthYear } from './months';
import { formatDay, formatWhen as formatRunWhen } from '../screens/sources/words';

describe('short month style', () => {
  it('writes every month in three letters, September as "Sep"', () => {
    expect(dayMonthYear('2026-09-17')).toBe('17 Sep 2026');
    expect(dayMonth('2027-06-01')).toBe('1 Jun');
    expect(formatFullDate('2026-09-17')).toBe('17 Sep 2026');
    expect(formatShortDate('2026-09-03')).toBe('3 Sep');
    expect(formatWhen('2026-09-30')).toBe('30 Sep 2026');
    expect(formatDay('2026-09-17T08:00:00Z')).toBe('17 Sep 2026');
    expect(formatRunWhen('2026-09-17T06:00:00Z')).toBe('17 Sep 2026, 08:00');
    for (const [i, m] of ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'].entries()) {
      expect(formatFullDate(`2026-${String(i + 1).padStart(2, '0')}-05`)).toBe(`5 ${m} 2026`);
    }
  });

  it('reads the Kigali date for instants near midnight', () => {
    expect(formatDay('2026-09-16T22:30:00Z')).toBe('17 Sep 2026');
  });
});
