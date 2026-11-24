import type { RouteObject } from 'react-router';
import { Placeholder } from './screens/Placeholder';

export const routes: RouteObject[] = [
  { path: '/', element: <Placeholder name="Feed" /> },
  { path: '/o/:id', element: <Placeholder name="Opportunity" /> },
  { path: '/digest/preview', element: <Placeholder name="Digest preview" /> },
  { path: '/styleguide/foundations', element: <Placeholder name="Styleguide: foundations" /> },
  { path: '/styleguide/components', element: <Placeholder name="Styleguide: components" /> },
];
