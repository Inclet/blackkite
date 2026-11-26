import { useRef, useState } from 'react';
import { useNavigate } from 'react-router';
import { ApiError } from '../../api/client';
import { m4Api, type OwnedDetail } from '../../api/m4';
import type { Resource } from '../../api/useResource';
import { Button } from '../../components/Button/Button';
import { SwitchRow } from '../../components/SwitchRow/SwitchRow';
import { Tag } from '../../components/Tag/Tag';
import type { FeedItem } from '../../fixtures/types';
import { COPY } from '../common/copy';
import { forgetItem } from '../items/ItemEditor';
import type { FeedModel } from './model';
import styles from './parts.module.css';

/** Not on any board (design review). */
export const OWN_COPY = {
  private: 'Private: only you can see this',
  public: 'Public: an admin published it with your consent',
  edit: 'Edit',
  delete: 'Delete',
  confirm: (title: string) => `Delete “${title}” for good? Your note and progress on it go too.`,
  confirmYes: 'Delete it',
  confirmNo: 'Keep it',
  deleteFailed: `${COPY.unreachableTitle}, so the item was not deleted. Try again.`,
  share: 'Let an admin make this public',
  shareHelp: 'An admin may then publish it, so every member can see the item itself. Your notes and progress stay private. Until it is published you can turn this off.',
  shared: 'An admin made this public, so it can no longer be made private, changed or deleted here. Ask an admin if something is wrong with it.',
  shareOn: 'Admins may now make this item public.',
  shareOff: 'Only you can see this item.',
  shareFailed: `${COPY.unreachableTitle}, so that change was undone. Try again.`,
  deleted: (title: string) => `Deleted: ${title}`,
} as const;

/**
 * The owner's controls on their own manual item (spec 6): the privacy Tag, Edit,
 * Delete with a confirm, and the share-consent switch (locked once published).
 * Only rendered when the detail answer carries `detail.ownItem`.
 */
export function OwnItemControls({ item, detail, model }: { item: FeedItem; detail: Resource<OwnedDetail>; model: FeedModel }) {
  const navigate = useNavigate();
  const own = detail.data!.detail.ownItem!;
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ text: string; alert: boolean } | null>(null);
  const deleteRef = useRef<HTMLButtonElement>(null);
  const published = own.published;

  const setOwn = (next: Partial<typeof own>) => detail.setData((d) => d && { ...d, detail: { ...d.detail, ownItem: { ...d.detail.ownItem!, ...next } } });

  const setConsent = async (allow: boolean) => {
    setOwn({ shareConsent: allow });
    setMessage(null);
    try {
      const answer = await m4Api.setShareConsent(item.id, allow);
      setOwn({ shareConsent: answer?.allow ?? allow, published: answer?.published ?? false });
      setMessage({ text: allow ? OWN_COPY.shareOn : OWN_COPY.shareOff, alert: false });
    } catch (e) {
      // 409: an admin published it meanwhile, so consent can no longer be withdrawn.
      if (e instanceof ApiError && e.kind === 'conflict') {
        setOwn({ shareConsent: true, published: true });
        setMessage({ text: OWN_COPY.shared, alert: true });
        return;
      }
      setOwn({ shareConsent: !allow });
      setMessage({ text: OWN_COPY.shareFailed, alert: true });
    }
  };

  const remove = async () => {
    setMessage(null);
    try {
      await m4Api.deleteItem(item.id);
      forgetItem(item.id);
      model.live?.forget(item.id);
      model.live?.announce(OWN_COPY.deleted(item.title));
      navigate('/');
    } catch (e) {
      if (e instanceof ApiError && e.kind === 'conflict') {
        setOwn({ published: true, shareConsent: true });
        setConfirming(false);
        setMessage({ text: OWN_COPY.shared, alert: true });
      } else setMessage({ text: OWN_COPY.deleteFailed, alert: true });
    }
  };

  return (
    <div className={styles.own} aria-label="Your item" role="group">
      <span className={styles.tags}>
        <Tag kind="profile">{published ? OWN_COPY.public : OWN_COPY.private}</Tag>
      </span>
      {!published && (
      <div className={styles.noteRow}>
        <Button variant="secondary" onClick={() => navigate(`/items/${encodeURIComponent(item.id)}/edit`)} aria-label={`${OWN_COPY.edit}: ${item.title}`}>
          {OWN_COPY.edit}
        </Button>
        <Button ref={deleteRef} variant="secondary" aria-expanded={confirming} onClick={() => setConfirming((c) => !c)} aria-label={`${OWN_COPY.delete}: ${item.title}`}>
          {OWN_COPY.delete}
        </Button>
      </div>
      )}
      {!published && confirming && (
        <div className={styles.stack} role="group" aria-label={OWN_COPY.delete}>
          <div className={styles.liveText}>{OWN_COPY.confirm(item.title)}</div>
          <div className={styles.noteRow}>
            <Button onClick={() => void remove()}>{OWN_COPY.confirmYes}</Button>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirming(false);
                deleteRef.current?.focus();
              }}
            >
              {OWN_COPY.confirmNo}
            </Button>
          </div>
        </div>
      )}
      <SwitchRow
        label={OWN_COPY.share}
        description={published ? OWN_COPY.shared : OWN_COPY.shareHelp}
        checked={published || own.shareConsent}
        disabled={published}
        onChange={(v) => void setConsent(v)}
      />
      <div role="status" className={message?.alert ? styles.liveAlert : styles.liveText}>
        {message?.text ?? ''}
      </div>
    </div>
  );
}
