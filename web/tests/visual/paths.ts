import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const visualDir = path.dirname(fileURLToPath(import.meta.url));
export const webRoot = path.resolve(visualDir, '../..');
export const referenceDir = path.resolve(webRoot, '../design/reference');
export const fontsDir = path.resolve(webRoot, 'public/fonts');
export const reportsDir = path.resolve(webRoot, 'tests/reports');
export const resultsDir = path.resolve(reportsDir, '.results');
