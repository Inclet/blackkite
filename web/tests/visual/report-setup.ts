import fs from 'node:fs';
import { resultsDir } from './paths';

/** Start each run clean so the report never shows a previous run's numbers. */
export default function globalSetup(): void {
  fs.rmSync(resultsDir, { recursive: true, force: true });
  fs.mkdirSync(resultsDir, { recursive: true });
}
