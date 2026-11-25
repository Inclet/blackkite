import { useState } from 'react';
import { AccountButton } from '../components/AccountButton/AccountButton';
import { BackLink } from '../components/BackLink/BackLink';
import { Button } from '../components/Button/Button';
import { DeadlinePill } from '../components/DeadlinePill/DeadlinePill';
import { NavItem } from '../components/NavItem/NavItem';
import { TrustPanel } from '../components/TrustNote/TrustNote';
import { Card, CardLabel } from '../components/Card/Card';
import { FeedRow } from '../components/FeedRow/FeedRow';
import { Field } from '../components/Field/Field';
import { FilterChip } from '../components/FilterChip/FilterChip';
import { FitLine, FitReason } from '../components/FitLine/FitLine';
import { Flag } from '../components/Flag/Flag';
import { StateCard, type StateKind } from '../components/StateCard/StateCard';
import { SwitchRow } from '../components/SwitchRow/SwitchRow';
import { Tag } from '../components/Tag/Tag';
import { TextButton, TextLink } from '../components/TextLink/TextLink';
import { reference } from '../fixtures/reference';
import { useFixture } from '../lib/fixture';
import { STREAMS } from '../lib/streams';
import styles from './Styleguide.module.css';

const STATE_LABELS: Record<StateKind, string> = {
  checking: 'State · checking',
  'nothing-new': 'State · nothing new',
  'first-visit': 'State · first visit',
  'source-down': 'State · a source is down',
};

/** /styleguide/components: the Components and states board. */
export function StyleguideComponents() {
  const content = (useFixture() ?? reference).styleguide;
  const [alerts, setAlerts] = useState(true);
  const { amount, trucks, alerts: alertsField } = content.fields;
  return (
    <>
    <main className={styles.board}>
      <div className={styles.three}>
        <Card label="Buttons" gap={14}>
          <div className={styles.row}>
            <Button>Save to shortlist</Button>
            <Button variant="secondary">Not for me</Button>
            <TextLink href="#">Read the original</TextLink>
          </div>
          <div className={styles.row}>
            <Button forceState="hover">Hover</Button>
            <Button forceState="focus">Keyboard focus</Button>
            <Button disabled>Disabled</Button>
          </div>
          <div className={styles.note}>One dark button per view. Focus always shows a double ring, on every control.</div>
        </Card>

        <Card label="Filters and tags" gap={14}>
          <div className={styles.wrap8}>
            {STREAMS.map((s) => (
              <FilterChip key={s} stream={s} selected={s === 'tender'} />
            ))}
          </div>
          <div className={styles.wrap8}>
            {STREAMS.map((s) => (
              <Tag key={s} kind="stream" stream={s} />
            ))}
            <Tag kind="profile">{content.profileTag}</Tag>
          </div>
          <div className={styles.note}>A filter fills with its colour only when selected. Profile tags stay neutral.</div>
        </Card>

        <Card label="Fields" gap={12}>
          <div className={styles.fields}>
            <Field id="bk-f1" label={amount.label} defaultValue={amount.value} />
            <Field id="bk-f2" label={trucks.label} defaultValue={trucks.value} error={trucks.error} />
          </div>
          <SwitchRow label={alertsField.label} description={alertsField.description} checked={alerts} onChange={setAlerts} />
        </Card>
      </div>

      <div className={styles.split}>
        <Card padding="22px 24px 10px">
          <CardLabel className={styles.feedLabel}>Feed row · built for scanning, and its awkward cases</CardLabel>
          {content.feedRows.map((row) => (
            <FeedRow key={row.title} {...row} />
          ))}
        </Card>

        <Card label="Fit · always with a reason" gap={12}>
          <div className={styles.fitLines}>
            {content.fitLines.map((f) => (
              <FitLine key={f.level} level={f.level} reason={f.reason} />
            ))}
          </div>
          <CardLabel className={styles.flagsLabel}>Flags · things to check before you act</CardLabel>
          <div className={styles.wrap8}>
            {content.flags.map((f) => (
              <Flag key={f}>{f}</Flag>
            ))}
          </div>
          <div className={styles.note}>The number stays out of the list. People read a word and a reason faster than a score.</div>
        </Card>
      </div>

      <div className={styles.states}>
        {content.states.map((s) => (
          <Card key={s.kind} label={STATE_LABELS[s.kind]} gap={12}>
            <StateCard {...s} />
          </Card>
        ))}
      </div>
    </main>
    <Phase2Variants />
    </>
  );
}

/**
 * Variants added in Phase 2 for the feed and opportunity screens. They sit below
 * the 1000px board area, so the board screenshot is unchanged.
 */
function Phase2Variants() {
  const wfp = reference.feed.items[0]!;
  return (
    <section className={styles.variants} aria-labelledby="sg-variants">
      <h2 id="sg-variants" className={styles.variantsTitle}>
        Screen variants · below the board
      </h2>
      <div className={styles.split}>
        <Card label="Feed row · list (desktop) and phone" gap={12}>
          <Card padding="8px">
            <FeedRow layout="list" href="#sg" selected stream="tender" title={wfp.title} subtitle="Strong fit · World Food Programme" fit="strong" deadline={{ deadline: wfp.deadline }} />
            <FeedRow layout="list" href="#sg" stream="event" title="ABH Summit and Grand Finale" subtitle="Startups and investors · Kigali Convention Centre" fit={null} deadline={{ event: { start: '2026-12-01', end: '2026-12-02' } }} />
          </Card>
          <Card padding="4px 12px" style={{ maxWidth: 366 }}>
            <FeedRow layout="phone" href="#sg" stream="funding" title="Transition to Scale research and innovation call" subtitle="Possible fit · NCST" fit="possible" deadline={{ deadline: '2026-12-07' }} />
            <FeedRow layout="phone" href="#sg" stream="investment" title="Five-year treasury bond" subtitle="National Bank of Rwanda" fit={null} deadline={{ deadline: null, emptyText: 'No deadline' }} />
          </Card>
          <div className={styles.wrap8}>
            <DeadlinePill deadline="2026-11-30" size="small" />
            <DeadlinePill event={{ start: '2026-12-01', end: '2026-12-02' }} size="small" />
            <DeadlinePill deadline="2026-12-23" size="small" />
            <DeadlinePill event={{ start: '2026-11-25' }} />
          </div>
        </Card>
        <Card label="Detail pane pieces" gap={12}>
          <FitLine level="strong" variant="heading" reason="why this matched" />
          {wfp.detail.reasons.map((r) => (
            <FitReason key={r}>{r}</FitReason>
          ))}
          <Flag variant="note">{wfp.detail.toCheck}</Flag>
          <TrustPanel state="unconfirmed" tone="mist">{wfp.detail.trust.desktop}</TrustPanel>
          <TrustPanel state="unconfirmed" tone="stone">{wfp.detail.trust.phone}</TrustPanel>
          <TrustPanel state="conflict" tone="mist">Two sources give different closing dates.</TrustPanel>
          <TextLink spacing="block" href="#sg">Read the original notice</TextLink>
          <TextButton spacing="stacked">See all sources</TextButton>
          <div className={styles.fields}>
            <Button size="large">Save to shortlist</Button>
            <Button size="large" variant="secondary">Not for me</Button>
          </div>
        </Card>
      </div>
      <Card label="Navigation" gap={12}>
        <div className={styles.row}>
          <NavItem variant="side" href="#sg" current>Feed</NavItem>
          <NavItem variant="side" href="#sg">Shortlist</NavItem>
          <NavItem variant="tab" href="#sg" current>Feed</NavItem>
          <NavItem variant="tab" href="#sg">More</NavItem>
          <AccountButton name="Clet" />
          <BackLink href="#sg">Feed</BackLink>
        </div>
      </Card>
    </section>
  );
}
