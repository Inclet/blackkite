import fs from 'node:fs';
import path from 'node:path';
import { fontsDir } from './paths';

export interface FontFile {
  file: string;
  url: string;
  subset: string;
  weights: number[];
  bytes: number;
  sha256: string;
}

export interface FontManifest {
  family: string;
  cssRequest: string;
  userAgent: string;
  cssSha256: string;
  files: FontFile[];
}

export function readManifest(): FontManifest {
  return JSON.parse(fs.readFileSync(path.join(fontsDir, 'manifest.json'), 'utf8')) as FontManifest;
}

/** The vendored CSS, as the app loads it (src URLs point at /fonts/<file>). */
export function vendoredCss(): string {
  return fs.readFileSync(path.join(fontsDir, 'google-figtree.css'), 'utf8');
}

/**
 * The vendored CSS with each /fonts/<file> URL put back to the original
 * fonts.gstatic.com URL from the manifest: byte for byte what Google served.
 */
export function googleCss(manifest = readManifest()): string {
  return vendoredCss().replace(/url\(\/fonts\/([^)]+)\)/g, (_m, file: string) => {
    const entry = manifest.files.find((f) => f.file === file);
    if (!entry) throw new Error(`google-figtree.css references ${file}, which is not in manifest.json`);
    return `url(${entry.url})`;
  });
}

export function fontBytes(file: string): Buffer {
  return fs.readFileSync(path.join(fontsDir, file));
}
