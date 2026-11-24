import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Button } from '../components/Button/Button';
import { Wordmark } from '../components/Wordmark/Wordmark';
import styles from './AuthConfirm.module.css';

type Status = 'idle' | 'sending' | 'failed';

/**
 * /auth/confirm?token=…: the sign-in link lands here, and the token is spent
 * only when the person presses the button, so mail link scanners cannot use it
 * (decision 17). Not on any board: built from existing components, listed for design review.
 */
export function AuthConfirm() {
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const token = search.get('token') ?? '';
  const [status, setStatus] = useState<Status>('idle');

  const confirm = async () => {
    setStatus('sending');
    try {
      const res = await fetch('/auth/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'same-origin',
        redirect: 'manual',
      });
      // 303 arrives as an opaque redirect under redirect: 'manual'.
      if (res.ok || res.status === 303 || res.type === 'opaqueredirect') {
        navigate('/');
        return;
      }
      setStatus('failed');
    } catch {
      setStatus('failed');
    }
  };

  return (
    <main className={styles.page}>
      <div className={styles.panel}>
        <Wordmark size={22} />
        <h1 className={styles.h1}>Sign in to Blackkite</h1>
        {token ? (
          <>
            <p className={styles.body}>Press the button to finish signing in on this device.</p>
            <div>
              <Button onClick={confirm} disabled={status === 'sending'}>
                Continue to sign in
              </Button>
            </div>
          </>
        ) : (
          <p className={styles.body}>This sign-in link is incomplete. Ask for a new one.</p>
        )}
        <div role="status" className={styles.body}>
          {status === 'failed' ? 'This link has expired or was already used. Ask for a new sign-in link.' : ''}
        </div>
      </div>
    </main>
  );
}
