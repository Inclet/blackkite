import { useFixture } from '../lib/fixture';

/** Stub screen; ui-builder replaces each of these with the real screen. */
export function Placeholder({ name }: { name: string }) {
  const fixture = useFixture();
  return (
    <main>
      <p>
        {name} (placeholder{fixture ? `, fixture: ${fixture.name}` : ''})
      </p>
    </main>
  );
}
