import { writeReport } from './report';

/** Runs after every test, passed or failed, so the report always covers all pages. */
export default function globalTeardown(): void {
  writeReport();
}
