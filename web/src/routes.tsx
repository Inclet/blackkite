import type { RouteObject } from 'react-router';
import { AuthConfirm } from './screens/AuthConfirm';
import { FeedRoute } from './screens/feed/FeedRoute';
import { Placeholder } from './screens/Placeholder';
import { SignIn } from './screens/SignIn';
import { Shortlist } from './screens/shortlist/Shortlist';
import { ProfileEditor } from './screens/profiles/ProfileEditor';
import { Profiles } from './screens/profiles/Profiles';
import { Account } from './screens/settings/Account';
import { DigestSettings } from './screens/settings/DigestSettings';
import { More } from './screens/settings/More';
import { StyleguideComponents } from './screens/StyleguideComponents';
import { StyleguideFoundations } from './screens/StyleguideFoundations';

export const routes: RouteObject[] = [
  {
    // / and /o/:id share one feed (state survives J/K moves between them).
    element: <FeedRoute />,
    children: [
      { path: '/', element: null },
      { path: '/o/:id', element: null },
    ],
  },
  { path: '/auth/confirm', element: <AuthConfirm /> },
  { path: '/sign-in', element: <SignIn /> },
  { path: '/shortlist', element: <Shortlist /> },
  { path: '/profiles', element: <Profiles /> },
  { path: '/profiles/new/:type', element: <ProfileEditor /> },
  { path: '/profiles/:id', element: <ProfileEditor /> },
  { path: '/settings/digest', element: <DigestSettings /> },
  { path: '/account', element: <Account /> },
  { path: '/more', element: <More /> },
  { path: '/digest/preview', element: <Placeholder name="Digest preview" /> },
  { path: '/styleguide/foundations', element: <StyleguideFoundations /> },
  { path: '/styleguide/components', element: <StyleguideComponents /> },
  // Not designed yet (CLAUDE.md section 12): reachable from the navigation, marked for design review.
  ...['/calendar', '/sources'].map((path) => ({
    path,
    element: <Placeholder name={`${path.slice(1, 2).toUpperCase()}${path.slice(2)} (not designed yet)`} />,
  })),
];
