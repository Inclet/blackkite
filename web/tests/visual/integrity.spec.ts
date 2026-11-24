import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { visualDir } from './paths';

/**
 * CONTRACT.sha256 pins the harness files that decide pass or fail. If this test
 * fails, one of them changed: that change needs the owner's explicit approval.
 */
test('harness contract files match CONTRACT.sha256', () => {
  const lines = fs.readFileSync(path.join(visualDir, 'CONTRACT.sha256'), 'utf8').trim().split('\n');
  expect(lines.length).toBeGreaterThan(0);
  for (const line of lines) {
    const [hash, file] = line.split(/\s+\*?/, 2) as [string, string];
    const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(visualDir, file))).digest('hex');
    expect(actual, `${file} changed`).toBe(hash);
  }
});
