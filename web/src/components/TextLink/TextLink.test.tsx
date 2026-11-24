/// <reference types="node" />
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { TextLink } from './TextLink';

test('renders a real link with its spacing', () => {
  render(
    <>
      <TextLink href="/original">Read the original</TextLink>
      <TextLink href="/shortlist" spacing="stacked">Open shortlist</TextLink>
    </>,
  );
  expect(screen.getByRole('link', { name: 'Read the original' })).toHaveClass('link', 'inline');
  expect(screen.getByRole('link', { name: 'Open shortlist' })).toHaveAttribute('href', '/shortlist');
  expect(screen.getByRole('link', { name: 'Open shortlist' })).toHaveClass('stacked');
});

test('the invisible hit area is at least 44px wide and high, centred', () => {
  const css = readFileSync(path.join(__dirname, 'TextLink.module.css'), 'utf8');
  const after = /\.link::after\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
  expect(after).toMatch(/min-width:\s*var\(--bk-tap-min\)/);
  expect(after).toMatch(/height:\s*max\(100%,\s*var\(--bk-tap-min\)\)/);
  expect(after).toMatch(/left:\s*50%/);
  expect(after).toMatch(/transform:\s*translate\(-50%,\s*-50%\)/);
});
