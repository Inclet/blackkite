import type { ExtractedField } from './types';

/** A field's value as one line of text: lists joined with "; ", numbers as given. */
export function fieldValueText(value: ExtractedField['value']): string {
  return Array.isArray(value) ? value.join('; ') : String(value);
}

/** The supporting passages of a field, whichever key carried them. */
export function fieldSnippets(field: ExtractedField): string[] {
  if (field.snippets?.length) return field.snippets;
  return field.snippet ? [field.snippet] : [];
}
