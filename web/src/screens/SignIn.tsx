import { useState, type FormEvent } from 'react';
import { api, ApiError } from '../api/client';
import { Button } from '../components/Button/Button';
import { Field } from '../components/Field/Field';
import { Wordmark } from '../components/Wordmark/Wordmark';
import styles from './AuthConfirm.module.css';

export const SIGN_IN = {
  heading: 'Sign in to Blackkite',
  body: 'We email you a link to sign in. There is no password.',
  label: 'Email address',
  button: 'Email me a sign-in link',
  sent: 'Check your email for a link.',
  emailError: 'Use an email address, such as name@example.com.',
  tooMany: 'Too many tries. Wait a few minutes, then try again.',
  unreachable: 'We could not reach Blackkite just now. Check your connection and try again.',
} as const;

type Status = 'idle' | 'sending' | 'sent' | 'too-many' | 'unreachable';

const looksLikeEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);

/**
 * Shown for any screen the API answers with 401, and at /sign-in. Posts the
 * address to /auth/request-link; the API answers the same for known and unknown
 * addresses, so the confirmation is the same too. Not on any board: Wordmark,
 * Field and Button only (design review).
 */
export function SignIn() {
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string | undefined>();
  const [status, setStatus] = useState<Status>('idle');

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const address = email.trim();
    if (!looksLikeEmail(address)) {
      setFieldError(SIGN_IN.emailError);
      return;
    }
    setFieldError(undefined);
    setStatus('sending');
    try {
      await api.requestLink(address);
      setStatus('sent');
    } catch (err) {
      const kind = err instanceof ApiError ? err.kind : 'unreachable';
      if (kind === 'invalid') {
        setFieldError(SIGN_IN.emailError);
        setStatus('idle');
      } else setStatus(kind === 'too-many' ? 'too-many' : 'unreachable');
    }
  };

  const message = status === 'sent' ? SIGN_IN.sent : status === 'too-many' ? SIGN_IN.tooMany : status === 'unreachable' ? SIGN_IN.unreachable : '';

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <Wordmark size={22} />
        <h1 className={styles.h1}>{SIGN_IN.heading}</h1>
        {status !== 'sent' && (
          <form className={styles.panel} onSubmit={submit} noValidate>
            <p className={styles.body}>{SIGN_IN.body}</p>
            <Field
              label={SIGN_IN.label}
              type="email"
              name="email"
              autoComplete="email"
              inputMode="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              error={fieldError}
            />
            <div>
              <Button type="submit" disabled={status === 'sending'}>
                {SIGN_IN.button}
              </Button>
            </div>
          </form>
        )}
        <div role="status" className={styles.body}>
          {message}
        </div>
      </div>
    </main>
  );
}
