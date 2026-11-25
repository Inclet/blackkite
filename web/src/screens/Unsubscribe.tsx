import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { Button } from '../components/Button/Button';
import { TextLink } from '../components/TextLink/TextLink';
import { Wordmark } from '../components/Wordmark/Wordmark';
import { useAppLink } from '../lib/useAppLink';
// The same quiet panel as the sign-in confirm page.
import styles from './AuthConfirm.module.css';

type Status = 'idle' | 'sending' | 'done' | 'invalid' | 'too-many' | 'unreachable';

export const UNSUBSCRIBE_PATH = '/unsubscribe';
export const SETTINGS_PATH = '/settings/digest';

export const UNSUBSCRIBE_COPY = {
  title: 'Emails from Blackkite',
  intro: 'Press the button to stop the emails this link came from.',
  button: 'Stop these emails',
  doneDigest: "You won't get these emails any more.",
  doneAlert: "You won't get these alerts any more.",
  // Used only if a 400 arrives without the API's own detail.
  invalid: 'This unsubscribe link is not valid. Change your emails in settings.',
  tooMany: 'Too many tries. Wait a little, then try again.',
  unreachable: 'We could not reach Blackkite just now. Check your connection and try again.',
  noToken: 'This link is missing its code. Open it again from the email, or change your email settings.',
  settings: 'Change your email settings',
} as const;

/** The token from `#token=…` only (the email links carry it in the fragment). */
export function unsubscribeTokenFrom(hash: string): string {
  return new URLSearchParams(hash.replace(/^#/, '')).get('token') ?? '';
}

const detailOf = (body: unknown): string | null =>
  body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string' && body.detail ? body.detail : null;

/**
 * /unsubscribe#token=…: the link at the foot of every digest and alert (decision 43).
 * No session needed: the signed token is the authority. Nothing happens on load
 * (mail link scanners open URLs); the token is spent only when the button is pressed,
 * and it is removed from the address bar at once.
 * Not on any board: built from existing components, listed for design review.
 */
export function Unsubscribe() {
  const location = useLocation();
  const navigate = useNavigate();
  const link = useAppLink();
  // Read once, before the address bar is cleaned.
  const [token] = useState(() => unsubscribeTokenFrom(location.hash));
  const [status, setStatus] = useState<Status>('idle');
  const [message, setMessage] = useState('');
  const hasExtraInUrl = location.hash !== '' || location.search !== '';

  useEffect(() => {
    if (hasExtraInUrl) navigate(UNSUBSCRIBE_PATH, { replace: true });
  }, [hasExtraInUrl, navigate]);

  const stop = async () => {
    setStatus('sending');
    setMessage('');
    const end = (next: Status, text: string) => {
      setStatus(next);
      setMessage(text);
    };
    try {
      const res = await fetch('/api/unsubscribe', {
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
        const body: unknown = await res.json().catch(() => null);
        const kind = body && typeof body === 'object' && 'kind' in body ? body.kind : null;
        if (kind === 'digest' || kind === 'alert') {
          return end('done', kind === 'alert' ? UNSUBSCRIBE_COPY.doneAlert : UNSUBSCRIBE_COPY.doneDigest);
        }
        return end('unreachable', UNSUBSCRIBE_COPY.unreachable);
      }
      if (res.status === 400) {
        const body: unknown = await res.json().catch(() => null);
        return end('invalid', detailOf(body) ?? UNSUBSCRIBE_COPY.invalid);
      }
      if (res.status === 429) return end('too-many', UNSUBSCRIBE_COPY.tooMany);
      end('unreachable', UNSUBSCRIBE_COPY.unreachable);
    } catch {
      end('unreachable', UNSUBSCRIBE_COPY.unreachable);
    }
  };

  // Finished (or nothing to do): no button, only the way to the settings.
  const finished = !token || status === 'done' || status === 'invalid';

  return (
    <main className={styles.page}>
      {/* Hoisted into <head> by React while this page is shown. */}
      <meta name="referrer" content="no-referrer" />
      <div className={styles.panel}>
        <Wordmark size={22} />
        <h1 className={styles.h1}>{UNSUBSCRIBE_COPY.title}</h1>
        {token ? (
          <>
            {!finished && <p className={styles.body}>{UNSUBSCRIBE_COPY.intro}</p>}
            {!finished && (
              <div>
                <Button onClick={stop} disabled={status === 'sending'}>
                  {UNSUBSCRIBE_COPY.button}
                </Button>
              </div>
            )}
          </>
        ) : (
          <p className={styles.body}>{UNSUBSCRIBE_COPY.noToken}</p>
        )}
        <div role="status" className={styles.body}>
          {message}
        </div>
        {finished && (
          <div>
            <TextLink spacing="stacked" {...link(SETTINGS_PATH)}>
              {UNSUBSCRIBE_COPY.settings}
            </TextLink>
          </div>
        )}
      </div>
    </main>
  );
}
