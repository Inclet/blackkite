import { useMatch, useSearchParams } from 'react-router';
import { fixtureFromSearch } from '../../lib/fixture';
import { useIsDesktop } from '../../lib/useIsDesktop';
import { Placeholder } from '../Placeholder';
import { FeedDesktop } from './FeedDesktop';
import { FeedPhone } from './FeedPhone';
import { stateFromSearch, useFeedModel } from './model';
import { OpportunityPhone } from './OpportunityPhone';
import type { Fixture } from '../../fixtures/types';

/**
 * Layout route for / and /o/:id. The feed state lives here so it survives
 * moving between the two (J/K change the URL without a reload).
 */
export function FeedRoute() {
  const [search] = useSearchParams();
  const fixture = fixtureFromSearch(search);
  const match = useMatch('/o/:id');
  if (!fixture) return <Placeholder name={match ? 'Opportunity' : 'Feed'} />;
  return <FeedScreens fixture={fixture} openId={match?.params.id ?? null} state={stateFromSearch(search)} />;
}

function FeedScreens({ fixture, openId, state }: { fixture: Fixture; openId: string | null; state: ReturnType<typeof stateFromSearch> }) {
  const model = useFeedModel(fixture, state);
  const desktop = useIsDesktop();
  if (desktop) return <FeedDesktop model={model} openId={openId} />;
  if (openId) return <OpportunityPhone model={model} id={openId} />;
  return <FeedPhone model={model} />;
}
