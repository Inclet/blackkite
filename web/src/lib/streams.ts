/** The four streams. Colours copied from the boards (identical to design/tokens.css). */
export type Stream = 'tender' | 'investment' | 'funding' | 'event';

export const STREAMS: readonly Stream[] = ['tender', 'investment', 'funding', 'event'];

export const STREAM_COLOURS: Record<Stream, { base: string; tint: string; text: string; icon: string }> = {
  tender: { base: '#F2A83B', tint: '#FCEFD6', text: '#7A5200', icon: '#C98412' },
  investment: { base: '#1FA898', tint: '#DDF3EF', text: '#0E5F56', icon: '#1FA898' },
  funding: { base: '#F0705A', tint: '#FCE4DF', text: '#8F2F1F', icon: '#F0705A' },
  event: { base: '#6C7BF2', tint: '#E5E8FD', text: '#333F9E', icon: '#6C7BF2' },
};

/** Singular names, as on tags and icon labels. */
export const STREAM_NAMES: Record<Stream, string> = {
  tender: 'Tender',
  investment: 'Investment',
  funding: 'Funding',
  event: 'Event',
};

/** Plural names, as on filter chips. */
export const STREAM_PLURALS: Record<Stream, string> = {
  tender: 'Tenders',
  investment: 'Investments',
  funding: 'Funding',
  event: 'Events',
};

export function cx(...names: (string | false | null | undefined)[]): string {
  return names.filter(Boolean).join(' ');
}
