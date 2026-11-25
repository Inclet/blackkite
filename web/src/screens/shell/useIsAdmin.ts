import { api } from '../../api/client';
import { useResource } from '../../api/useResource';
import { useFixture } from '../../lib/fixture';

/**
 * True for a live admin session (GET /me says role "admin"). Never with a
 * ?fixture=: the fixture screens are the boards, and the boards have no Admin
 * entry, so the visual harness sees the board's sidebar. The server enforces
 * roles regardless (spec 3); this only decides whether admin links are shown.
 */
export function useIsAdmin(): boolean {
  const fixture = useFixture();
  const me = useResource(fixture ? null : 'me', (s) => api.me(s));
  return !fixture && me.data?.role === 'admin';
}
