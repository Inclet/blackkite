import { render } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { vi } from 'vitest';
import { routes } from '../../routes';

/** Render the app at a URL; returns the router so tests can read the location. */
export function renderAt(url: string) {
  const router = createMemoryRouter(routes, { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}

/** Pretend the viewport is a phone (< 792px) or desktop. */
export function setViewport(kind: 'phone' | 'desktop') {
  vi.stubGlobal(
    'matchMedia',
    (query: string) =>
      ({
        matches: kind === 'desktop',
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}
