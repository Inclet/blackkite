import { useEffect, useState } from 'react';
import { useLocation, useNavigate, type Location } from 'react-router';
import { Button } from '../components/Button/Button';
import { Wordmark } from '../components/Wordmark/Wordmark';
import styles from './AuthConfirm.module.css';

type Status = 'idle' | 'sending' | 'invalid' | 'too-many' | 'unreachable';

export const CONFIRM_PATH = '/auth/confirm';

export const MESSAGES = {
  noToken: 'This sign-in link is incomplete. Ask for a new one.',
  invalid: 'This sign-in link has expired or was already used. Ask for a new one.',
  tooMany: 'Too many tries. Wait a few minutes, then try again.',
  unreachable: 'We could not reach Blackkite to sign you in. Check your connection and try again.',
} as const;

/** The token from `#token=…` (current links), else `?token=…` (older links). */
export function tokenFrom(location: Pick<Location, 'hash' | 'search'>): string {
  const fromHash = new URLSearchParams(location.hash.replace(/^#/, '')).get('token');
  if (fromHash) return fromHash;
  return new URLSearchParams(location.search).get('token') ?? '';
}

/** A same-origin path to go to after sign-in, or '/' for anything else. */
export function safeRedirect(redirect: unknown, origin = window.location.origin): string {
  if (typeof redirect !== 'string' || !redirect.startsWith('/') || redirect.startsWith('//') || redirect.startsWith('/\\')) return '/';
  try {
    const url = new URL(redirect, origin);
    if (url.origin !== origin) return '/';
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return '/';
  }
}

/**
 * /auth/confirm#token=…: the sign-in link lands here, and the token is spent
 * only when the person presses the button, so mail link scanners cannot use it
 * (decision 17). The token is read once and removed from the address bar at once.
 * Not on any board: built from existing components, listed for design review.
 */
export function AuthConfirm() {
  const location = useLocation();
  const navigate = useNavigate();
  // Read once, before the address bar is cleaned.
  const [token] = useState(() => tokenFrom(location));
  const [status, setStatus] = useState<Status>('idle');
  const hasTokenInUrl = location.hash !== '' || location.search !== '';

  useEffect(() => {
    if (hasTokenInUrl) navigate(CONFIRM_PATH, { replace: true });
  }, [hasTokenInUrl, navigate]);

  const confirm = async () => {
    setStatus('sending');
    try {
      const res = await fetch('/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'same-origin',
        // A redirect is not success: it arrives as an opaque redirect and fails below.
        redirect: 'manual',
        // The page itself is no-referrer; keep a real Origin on this same-origin POST.
        referrerPolicy: 'same-origin',
      });
      if (res.status === 200) {
        const body: unknown = await res.json();
        if (body && typeof body === 'object' && 'redirect' in body && typeof body.redirect === 'string') {
          navigate(safeRedirect(body.redirect), { replace: true });
          return;
        }
      }
      if (res.status === 400) setStatus('invalid');
      else if (res.status === 429) setStatus('too-many');
      else setStatus('unreachable');
    } catch {
      setStatus('unreachable');
    }
  };

  const message =
    status === 'invalid'
      ? MESSAGES.invalid
      : status === 'too-many'
        ? MESSAGES.tooMany
        : status === 'unreachable'
          ? MESSAGES.unreachable
          : '';

  return (
    <main className={styles.page}>
      {/* Hoisted into <head> by React while this page is shown. */}
      <meta name="referrer" content="no-referrer" />
      <div className={styles.panel}>
        <Wordmark size={22} />
        <h1 className={styles.h1}>Sign in to Blackkite</h1>
        {token ? (
          <>
            <p className={styles.body}>Press the button to finish signing in on this device.</p>
            {status !== 'invalid' && (
              <div>
                <Button onClick={confirm} disabled={status === 'sending'}>
                  Continue to sign in
                </Button>
              </div>
            )}
          </>
        ) : (
          <p className={styles.body}>{MESSAGES.noToken}</p>
        )}
        <div role="status" className={styles.body}>
          {message}
        </div>
      </div>
    </main>
  );
}
