import type { RouteObject } from 'react-router';
import { Placeholder } from './screens/Placeholder';
import { StyleguideComponents } from './screens/StyleguideComponents';
import { StyleguideFoundations } from './screens/StyleguideFoundations';

export const routes: RouteObject[] = [
  { path: '/', element: <Placeholder name="Feed" /> },
  { path: '/o/:id', element: <Placeholder name="Opportunity" /> },
  { path: '/digest/preview', element: <Placeholder name="Digest preview" /> },
  { path: '/styleguide/foundations', element: <StyleguideFoundations /> },
  { path: '/styleguide/components', element: <StyleguideComponents /> },
];
