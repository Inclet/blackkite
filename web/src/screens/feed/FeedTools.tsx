import { useNavigate } from 'react-router';
import { Button } from '../../components/Button/Button';
import { ITEM_COPY } from '../items/ItemEditor';
import type { FeedModel } from './model';
import styles from './parts.module.css';

/**
 * Live data only (never on fixtures, so the boards stay as drawn): the row under
 * the stream chips with "Add an item". Design review.
 */
export function FeedTools({ model, className }: { model: FeedModel; className?: string }) {
  const navigate = useNavigate();
  if (!model.live) return null;
  return (
    <div className={[styles.tools, className].filter(Boolean).join(' ')}>
      <Button variant="secondary" onClick={() => navigate('/items/new')}>
        {ITEM_COPY.add}
      </Button>
    </div>
  );
}
