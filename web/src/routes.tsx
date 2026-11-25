import type { RouteObject } from 'react-router';
import { AdminHome } from './screens/admin/AdminHome';
import { AdminReview } from './screens/admin/AdminReview';
import { AdminSources } from './screens/admin/AdminSources';
import { AdminSuggestions } from './screens/admin/AdminSuggestions';
import { AdminUsers } from './screens/admin/AdminUsers';
import { SourceEditor } from './screens/admin/SourceEditor';
import { AuthConfirm } from './screens/AuthConfirm';
import { FeedRoute } from './screens/feed/FeedRoute';
import { Placeholder } from './screens/Placeholder';
import { AppShell } from './screens/shell/AppShell';
import { SignIn } from './screens/SignIn';
import { Shortlist } from './screens/shortlist/Shortlist';
import { Sources } from './screens/sources/Sources';
import { Unsubscribe } from './screens/Unsubscribe';
import { ProfileEditor } from './screens/profiles/ProfileEditor';
import { Profiles } from './screens/profiles/Profiles';
import { Account } from './screens/settings/Account';
import { DigestSettings } from './screens/settings/DigestSettings';
import { More } from './screens/settings/More';
import { StyleguideComponents } from './screens/StyleguideComponents';
import { StyleguideFoundations } from './screens/StyleguideFoundations';

/** Calendar, until it is built (CLAUDE.md section 12). */
export const NOT_DESIGNED = 'Not designed yet.';

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
  // No session needed (decision 43): the signed token in the fragment is the authority.
  { path: '/unsubscribe', element: <Unsubscribe /> },
  { path: '/shortlist', element: <Shortlist /> },
  { path: '/profiles', element: <Profiles /> },
  { path: '/profiles/new/:type', element: <ProfileEditor /> },
  { path: '/profiles/:id', element: <ProfileEditor /> },
  { path: '/settings/digest', element: <DigestSettings /> },
  { path: '/account', element: <Account /> },
  { path: '/more', element: <More /> },
  { path: '/sources', element: <Sources /> },
  // Admins only (the server enforces roles regardless); not designed yet (design review).
  { path: '/admin', element: <AdminHome /> },
  { path: '/admin/sources', element: <AdminSources /> },
  { path: '/admin/sources/new', element: <SourceEditor /> },
  { path: '/admin/sources/:id', element: <SourceEditor /> },
  { path: '/admin/suggestions', element: <AdminSuggestions /> },
  { path: '/admin/review', element: <AdminReview /> },
  { path: '/admin/users', element: <AdminUsers /> },
  { path: '/digest/preview', element: <Placeholder name="Digest preview" /> },
  { path: '/styleguide/foundations', element: <StyleguideFoundations /> },
  { path: '/styleguide/components', element: <StyleguideComponents /> },
  // Not designed yet (CLAUDE.md section 12): reachable from the navigation, marked for design review.
  // In the app frame, so the sidebar is the same as on every other screen.
  ...[
    { path: '/calendar', title: 'Calendar' },
  ].map(({ path, title }) => ({
    path,
    element: <AppShell path={path} title={title} summary={NOT_DESIGNED} />,
  })),
];
