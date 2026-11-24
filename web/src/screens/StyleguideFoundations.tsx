import type { ReactNode } from 'react';
import { Card, CardLabel } from '../components/Card/Card';
import { DeadlinePill } from '../components/DeadlinePill/DeadlinePill';
import { Kite } from '../components/Kite/Kite';
import { KiteOrbit, ORBITS } from '../components/KiteOrbit/KiteOrbit';
import { Tag } from '../components/Tag/Tag';
import { TrustNote } from '../components/TrustNote/TrustNote';
import { Wordmark } from '../components/Wordmark/Wordmark';
import { reference } from '../fixtures/reference';
import { useFixture } from '../lib/fixture';
import { STREAMS, type Stream } from '../lib/streams';
import styles from './Styleguide.module.css';

const NEUTRALS: { hex: string; name: string; use: string; outlined?: boolean }[] = [
  { hex: '#F6F5F2', name: 'Mist', use: 'page', outlined: true },
  { hex: '#FFFFFF', name: 'White', use: 'cards', outlined: true },
  { hex: '#EFEDE9', name: 'Stone 100', use: 'quiet fills' },
  { hex: '#E7E5E0', name: 'Stone 200', use: 'borders' },
  { hex: '#D6D3CD', name: 'Stone 300', use: 'field borders' },
  { hex: '#5F5D59', name: 'Slate', use: 'second text' },
  { hex: '#2B2A28', name: 'Graphite', use: 'text, actions' },
];

const STREAM_SWATCHES: Record<Stream, { name: string; hexes: [string, string, string] }> = {
  tender: { name: 'Marigold', hexes: ['#F2A83B', '#FCEFD6', '#7A5200'] },
  investment: { name: 'Lagoon', hexes: ['#1FA898', '#DDF3EF', '#0E5F56'] },
  funding: { name: 'Coral', hexes: ['#F0705A', '#FCE4DF', '#8F2F1F'] },
  event: { name: 'Iris', hexes: ['#6C7BF2', '#E5E8FD', '#333F9E'] },
};

const SPACE = [4, 8, 12, 16, 24, 32, 48];

function Mark({ children, caption }: { children: ReactNode; caption: string }) {
  return (
    <div className={styles.mark}>
      {children}
      <div className={styles.caption}>{caption}</div>
    </div>
  );
}

/** /styleguide/foundations: the Foundations board. Its demo motion lives only here (decision 9). */
export function StyleguideFoundations() {
  const content = (useFixture() ?? reference).styleguide;
  return (
    <main className={styles.board}>
      <div className={styles.two}>
        <Card label="Logo" padding="24px 28px" gap={16}>
          <div className={styles.logoRow}>
            <Kite variant="full" width={180} height={120} label="Blackkite mark" className={styles.glide} />
            <div className={styles.logoSide}>
              <div className={styles.lockup}>
                <Kite variant="full" width={63} height={42} rotate={-16} />
                <Wordmark size={36} />
              </div>
              <div className={styles.marks}>
                <Mark caption="Small, 32">
                  <Kite width={48} height={32} />
                </Mark>
                <Mark caption="20">
                  <Kite width={30} height={20} />
                </Mark>
                <Mark caption="Favicon">
                  <div className={styles.favicon}>
                    <Kite width={26} height={17} rotate={-16} fill="#F6F5F2" />
                  </div>
                </Mark>
                <Mark caption="App icon">
                  <div className={styles.appIcon}>
                    <Kite width={44} height={29} rotate={-16} fill="#F6F5F2" />
                  </div>
                </Mark>
              </div>
            </div>
          </div>
          <div className={styles.note}>
            Longer forked tail and slimmer, swept wings. The full mark keeps its wingtip feathers; below 40 pixels use the small mark.
          </div>
        </Card>

        <Card label="Signature · the kite circles, then drops" padding="24px 28px" gap={16}>
          <div className={styles.signatureRow}>
            <KiteOrbit orbit={ORBITS.signature}>
              <div className={styles.dot} style={{ left: 104, top: 46, background: '#F2A83B' }} />
              <div className={styles.dot} style={{ left: 40, top: 96, background: '#6C7BF2' }} />
              <div className={styles.dot} style={{ left: 60, top: 30, background: '#1FA898' }} />
            </KiteOrbit>
            <div className={styles.signatureText}>
              <div>
                <strong>Scanning.</strong> The kite circles while sources are checked. It replaces every spinner.
              </div>
              <div>
                <strong>Found.</strong> A new item drops into the list from above, once.
              </div>
              <div>
                <strong>Quiet.</strong> When nothing is new the kite rests. No empty-state illustration, just the mark and one line.
              </div>
              <div className={styles.dropped}>{content.droppedItem}</div>
            </div>
          </div>
        </Card>
      </div>

      <Card padding="24px 28px" className={styles.colours}>
        <div className={styles.neutrals}>
          <CardLabel>Neutrals · everything structural</CardLabel>
          {NEUTRALS.map((n) => (
            <div key={n.hex} className={styles.swatchRow}>
              <div className={n.outlined ? styles.swatchOutlined : styles.swatch} style={{ background: n.hex }} />
              <strong className={styles.swatchName}>{n.name}</strong>
              <span className={styles.slate}>{`${n.hex} · ${n.use}`}</span>
            </div>
          ))}
        </div>

        <div className={styles.streams}>
          <CardLabel>Streams · colour plus icon, never colour alone</CardLabel>
          <div className={styles.streamGrid}>
            {STREAMS.map((s) => (
              <StreamRow key={s} stream={s} />
            ))}
          </div>
          <div className={styles.note}>
            Each stream has a base for dots, a tint for tags, and a dark shade that is safe for text. Sage is retired: it sat too close to Lagoon.
          </div>
        </div>

        <div className={styles.urgency}>
          <CardLabel>Urgency · by weight, not hue</CardLabel>
          <div className={styles.pills}>
            {content.urgencyDeadlines.map((d) => (
              <DeadlinePill key={d} deadline={d} />
            ))}
          </div>
          <CardLabel className={styles.trustLabel}>Trust · every item shows where it stands</CardLabel>
          <div className={styles.trust}>
            <TrustNote state="confirmed" />
            <TrustNote state="unconfirmed" />
            <TrustNote state="conflict" />
          </div>
          <div className={styles.alertRow}>
            <div className={styles.swatch} style={{ background: '#C4352B' }} />
            <strong>Alert</strong>
            <span className={styles.slate}>#C4352B · errors and last-day deadlines only</span>
          </div>
        </div>
      </Card>

      <div className={styles.four}>
        <Card label="Type · Figtree" padding="22px 24px" gap={8}>
          <div className={styles.display}>Display 32</div>
          <div className={styles.title}>Title 24</div>
          <div className={styles.heading}>Heading 19</div>
          <div className={styles.body}>Body 15 on a 24 line, at most 70 characters wide.</div>
          <div className={styles.label}>Label 13 · Caption 12 · never smaller</div>
          <div className={styles.numbers}>30 Nov 2026 · FRW 5,000,000</div>
        </Card>

        <Card label="Space and shape" padding="22px 24px" gap={12}>
          <div className={styles.space}>
            {SPACE.map((n) => (
              <div key={n} style={{ width: n, height: n, background: '#2B2A28' }} />
            ))}
          </div>
          <div className={styles.slateNumbers}>4 · 8 · 12 · 16 · 24 · 32 · 48</div>
          <div className={styles.shapes}>
            <div className={styles.shape} style={{ borderRadius: 8 }} />
            <div className={styles.shape} style={{ borderRadius: 14 }} />
            <div className={styles.shape} style={{ borderRadius: 999 }} />
          </div>
          <div className={styles.slate13}>8 controls · 14 cards · pill tags</div>
          <div className={styles.slate13}>Tap targets at least 44 high.</div>
        </Card>

        <Card label="Motion" padding="22px 24px" gap={10} className={styles.prose}>
          <div>
            <strong>Quick, 120 ms.</strong> Hover and press.
          </div>
          <div>
            <strong>Settle, 220 ms.</strong> Items entering, panels opening.
          </div>
          <div>
            <strong>Glide, 400 ms.</strong> Page changes and the kite.
          </div>
          <div className={styles.slate}>One easing everywhere: fast out, soft landing.</div>
          <div className={styles.slate}>With reduced motion on, things fade and nothing moves.</div>
        </Card>

        <Card label="Voice · plain, warm, specific" padding="22px 24px" gap={10} className={styles.prose}>
          <div>
            <strong>Not for me</strong> <span className={styles.slate}>rather than Dismiss</span>
          </div>
          <div>
            <strong>Why this matched</strong> <span className={styles.slate}>rather than Relevance score</span>
          </div>
          <div>
            <strong>Found on Job in Rwanda</strong> <span className={styles.slate}>rather than Source: aggregator</span>
          </div>
          <div>
            <strong>We could not reach BNR today</strong> <span className={styles.slate}>rather than Error 503</span>
          </div>
          <div className={styles.slate}>No hype, no exclamation marks. Layouts leave a third more room for Kinyarwanda and French.</div>
        </Card>
      </div>
    </main>
  );
}

function StreamRow({ stream }: { stream: Stream }) {
  const { name, hexes } = STREAM_SWATCHES[stream];
  return (
    <>
      <Tag kind="stream" stream={stream} icon className={styles.start} />
      {hexes.map((h) => (
        <div key={h} className={styles.bar} style={{ background: h }} />
      ))}
      <span className={styles.slate}>{[name, ...hexes].join(' · ')}</span>
      <Tag kind="stream" stream={stream} icon evening className={styles.start}>
        Evening
      </Tag>
    </>
  );
}
