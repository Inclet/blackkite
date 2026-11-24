import { useState } from 'react';
import { Button } from '../components/Button/Button';
import { Card, CardLabel } from '../components/Card/Card';
import { FeedRow } from '../components/FeedRow/FeedRow';
import { Field } from '../components/Field/Field';
import { FilterChip } from '../components/FilterChip/FilterChip';
import { FitLine } from '../components/FitLine/FitLine';
import { Flag } from '../components/Flag/Flag';
import { StateCard, type StateKind } from '../components/StateCard/StateCard';
import { Switch } from '../components/Switch/Switch';
import { Tag } from '../components/Tag/Tag';
import { TextLink } from '../components/TextLink/TextLink';
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
          <div className={styles.switchRow}>
            <div className={styles.switchText}>
              <div className={styles.switchLabel}>{alertsField.label}</div>
              <div className={styles.slate13}>{alertsField.description}</div>
            </div>
            <Switch checked={alerts} onChange={setAlerts} label={alertsField.label} />
          </div>
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
  );
}
