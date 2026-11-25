import { fireEvent, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { collectorTypesFrom, COLLECTOR_TYPES as TYPE_NAMES } from '../../api/sources';
import { mockApi } from '../../test/mockApi';
import { renderAt, setViewport } from '../feed/testUtils';
import { COLLECTOR_WORDS } from '../sources/words';
import { EDITOR_COPY } from './SourceEditor';
import { fieldKind, fieldLabel, fieldsFor } from './sourceForm';
import { ADMIN_ME, COLLECTOR_TYPES } from './testData';

/** The real GET /api/admin/collector-types answer (tests/fixtures/collector-types.json). */
const TYPES = collectorTypesFrom(COLLECTOR_TYPES);

beforeEach(() => setViewport('desktop'));
afterEach(() => vi.restoreAllMocks());
afterEach(() => vi.unstubAllGlobals());

test('the fixture is the API answer for every collector type the web knows, all built, all from the model', () => {
  expect(TYPES.map((t) => t.type)).toEqual([...TYPE_NAMES]);
  for (const t of TYPES) expect([t.type, t.implemented, t.schemaSource, t.fields.length > 0]).toEqual([t.type, true, 'model', true]);
});

test.each(TYPES.map((t) => t.type))('editor renders every field of the real %s type, without errors', async (type) => {
  const errors = vi.spyOn(console, 'error');
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/collector-types': COLLECTOR_TYPES });
  renderAt('/admin/sources/new');
  const form = within(await screen.findByRole('form', { name: EDITOR_COPY.newTitle }));
  fireEvent.click(form.getByRole('button', { name: COLLECTOR_WORDS[type] }));
  expect(screen.queryByText(EDITOR_COPY.notBuilt)).toBeNull();
  const fields = fieldsFor(TYPES, type)!;
  for (const f of fields) {
    const label = `${fieldLabel(f)}${f.required ? '' : ' (optional)'}`;
    const kind = fieldKind(f.kind);
    if (kind === 'boolean') expect(form.getByRole('switch', { name: label })).toBeInTheDocument();
    else if (kind === 'choice') expect(within(form.getByRole('group', { name: label })).getAllByRole('button').map((b) => b.textContent)).toEqual(f.options);
    else expect(form.getByLabelText(label)).toBeInTheDocument();
  }
  expect(errors).not.toHaveBeenCalled();
});

test('json_api: pagination and mapping fields, with the API help that spells out the JSON shapes', async () => {
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/collector-types': COLLECTOR_TYPES });
  renderAt('/admin/sources/new');
  const form = within(await screen.findByRole('form', { name: EDITOR_COPY.newTitle }));
  fireEvent.click(form.getByRole('button', { name: COLLECTOR_WORDS.json_api }));
  expect(form.getByLabelText('Pagination (optional)')).toHaveAccessibleDescription(expect.stringContaining('mode page: param, start, max_pages'));
  expect(form.getByLabelText('Params (optional)')).toHaveAccessibleDescription(expect.stringContaining('JSON.'));
  for (const name of ['Mapping: title', 'Mapping: url', 'Mapping: list (optional)', 'Mapping: url template (optional)', 'Mapping: extra (optional)']) {
    expect(form.getByLabelText(name)).toBeInTheDocument();
  }
});

test('custom: the collector is a choice; its options are JSON with each collector\'s settings in the hint', async () => {
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/collector-types': COLLECTOR_TYPES });
  renderAt('/admin/sources/new');
  const form = within(await screen.findByRole('form', { name: EDITOR_COPY.newTitle }));
  fireEvent.click(form.getByRole('button', { name: COLLECTOR_WORDS.custom }));
  expect(within(form.getByRole('group', { name: 'Collector' })).getByRole('button', { name: 'jsonld_events' })).toBeInTheDocument();
  expect(form.getByLabelText('Options (optional)')).toHaveAccessibleDescription(expect.stringContaining('jsonld_events: list_url (required)'));
});

test('email_ingest: a switch whose API default is on starts on', async () => {
  mockApi({ 'GET /me': ADMIN_ME, 'GET /api/admin/collector-types': COLLECTOR_TYPES });
  renderAt('/admin/sources/new');
  const form = within(await screen.findByRole('form', { name: EDITOR_COPY.newTitle }));
  fireEvent.click(form.getByRole('button', { name: COLLECTOR_WORDS.email_ingest }));
  expect(form.getByRole('switch', { name: 'Require authenticated (optional)' })).toHaveAttribute('aria-checked', 'true');
  fireEvent.click(form.getByRole('button', { name: COLLECTOR_WORDS.rss }));
  expect(form.getByRole('switch', { name: 'Author as organisation (optional)' })).toHaveAttribute('aria-checked', 'false');
});
