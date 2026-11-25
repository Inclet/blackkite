import type { MouseEvent } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { isModifiedClick } from '../../lib/useAppLink';
import type { StateCardProps, StateKind } from '../../components/StateCard/StateCard';
import type { FeedModel } from './model';

/** Where each state's action leads. Those screens are not designed yet (placeholders). */
const ACTION_TARGET: Partial<Record<StateKind, string>> = {
  'nothing-new': '/shortlist',
  'first-visit': '/profiles',
  'source-down': '/sources',
};

/**
 * The state card to show above (or instead of) the list: the ?state= one, or
 * "nothing new" once every item has been dismissed or filtered away. Copy is the
 * Components board's, from the fixture.
 */
export function useStateCard(model: FeedModel): StateCardProps | null {
  const navigate = useNavigate();
  const { search } = useLocation();
  const card = model.stateCard ?? (model.items.length === 0 ? (model.states.find((s) => s.kind === 'nothing-new') ?? null) : null);
  if (!card?.action) return card;
  const target = ACTION_TARGET[card.kind];
  if (!target) return card;
  const href = `${target}${search}`;
  if (card.kind === 'first-visit') return { ...card, action: { label: card.action.label, onClick: () => navigate(href) } };
  return {
    ...card,
    action: {
      label: card.action.label,
      href,
      // StateCard hands the link's click event through; without preventDefault the browser would also load the page.
      onClick: ((event?: MouseEvent) => {
        if (event && (event.defaultPrevented || isModifiedClick(event))) return;
        event?.preventDefault();
        navigate(href);
      }) as () => void,
    },
  };
}
