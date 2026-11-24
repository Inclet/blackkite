/** The URL if it is an absolute http(s) URL, else null (no javascript:, data:, relative or malformed links). */
export function httpUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : null;
  } catch {
    return null;
  }
}
