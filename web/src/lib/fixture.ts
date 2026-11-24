import { useSearchParams } from 'react-router';
import type { Fixture } from '../fixtures/types';
import { edgeCases } from '../fixtures/edge-cases';
import { reference } from '../fixtures/reference';

const fixtures: Record<string, Fixture> = { reference, 'edge-cases': edgeCases };

/** Returns the fixture named by ?fixture=<name>, or null to use live data. */
export function fixtureFromSearch(search: URLSearchParams): Fixture | null {
  const name = search.get('fixture');
  return name !== null ? (fixtures[name] ?? null) : null;
}

export function useFixture(): Fixture | null {
  const [search] = useSearchParams();
  return fixtureFromSearch(search);
}
