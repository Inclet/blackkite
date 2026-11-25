import { expect, test } from 'vitest';
import type { AdminSource, ConfigField } from '../../api/sources';
import { camel } from '../../api/sources';
import { buildConfig, configValues, detailText, emptyForm, fieldKind, fieldLabel, FORM_COPY, toForm, validate, WHOLE_CONFIG } from './sourceForm';
import { adminSource, COLLECTOR_TYPES } from './testData';

const HTML = camel<{ fields: ConfigField[] }[]>(COLLECTOR_TYPES)[0]!.fields;

test('field types map to inputs; unknown types are edited as JSON', () => {
  expect(['bool', 'integer', 'float', 'url', 'list[str]', 'string[]', 'dict', 'str', 'selector', 'weird'].map(fieldKind)).toEqual([
    'boolean',
    'integer',
    'number',
    'url',
    'list',
    'list',
    'json',
    'text',
    'text',
    'json',
  ]);
  expect(fieldLabel({ name: 'selectors.item_title', type: 'string', required: true, help: null })).toBe('Selectors: item title');
  expect(fieldLabel({ name: 'x', type: 'string', required: true, help: null, label: 'List page' })).toBe('List page');
});

test('config to form and back: dotted names nest, numbers parse, undescribed keys survive', () => {
  const stored = camel<AdminSource>(adminSource()).config;
  const values = configValues(HTML, stored);
  expect(values).toEqual({ list_url: 'https://www.umucyo.gov.rw/tenders', 'selectors.item': 'tr', 'selectors.title': 'td a', max_pages: '1' });
  const { config, errors } = buildConfig(HTML, { ...values, max_pages: '3' }, stored);
  expect(errors).toEqual({});
  expect(config).toEqual({ list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 3 });
  // Clearing an optional field drops its key.
  expect(buildConfig(HTML, { ...values, max_pages: '' }, stored).config).not.toHaveProperty('max_pages');
});

test('config errors: required, whole numbers, URLs, JSON', () => {
  const { errors } = buildConfig(HTML, { list_url: 'umucyo', 'selectors.item': '', 'selectors.title': 'a', max_pages: 'two' });
  expect(errors).toEqual({ list_url: FORM_COPY.urlInvalid, 'selectors.item': FORM_COPY.required, max_pages: FORM_COPY.integer });
  const json: ConfigField[] = [{ name: 'mapping', type: 'object', required: false, help: null }];
  expect(buildConfig(json, { mapping: '{"title": "name"}' }).config).toEqual({ mapping: { title: 'name' } });
  expect(buildConfig(json, { mapping: '{title' }).errors).toEqual({ mapping: FORM_COPY.json });
  const lists: ConfigField[] = [{ name: 'queries', type: 'list', required: true, help: null }];
  expect(buildConfig(lists, { queries: 'tender Kigali , transport,' }).config).toEqual({ queries: ['tender Kigali', 'transport'] });
  const flag: ConfigField[] = [{ name: 'strip', type: 'boolean', required: false, help: null }];
  expect(buildConfig(flag, { strip: true }).config).toEqual({ strip: true });
});

test('no field list: the whole config as one JSON object', () => {
  expect(configValues(null, { a: 1 })).toEqual({ [WHOLE_CONFIG]: '{"a":1}' });
  expect(buildConfig(null, { [WHOLE_CONFIG]: '{"a":2}' }).config).toEqual({ a: 2 });
  expect(buildConfig(null, { [WHOLE_CONFIG]: '[1]' }).errors).toEqual({ [WHOLE_CONFIG]: FORM_COPY.configObject });
  expect(buildConfig(null, {}).config).toEqual({});
});

test('validate: the record and the body the API takes (snake_case)', () => {
  const empty = validate(emptyForm(), null, undefined);
  expect(empty.body).toBeNull();
  expect(empty.errors).toMatchObject({ name: FORM_COPY.nameRequired, homeUrl: FORM_COPY.urlRequired, streams: FORM_COPY.streamsRequired, kind: FORM_COPY.kindRequired, collectorType: FORM_COPY.typeRequired });

  const form = toForm(camel<AdminSource>(adminSource()), camel(COLLECTOR_TYPES));
  const ok = validate({ ...form, schedule: '0 6 * * *', accessNote: ' ' }, HTML, camel<AdminSource>(adminSource()).config);
  expect(ok.errors).toEqual({});
  expect(ok.body).toEqual({
    name: 'Umucyo e-procurement',
    home_url: 'https://www.umucyo.gov.rw/',
    publisher: 'RPPA',
    streams: ['tender'],
    kind: 'original',
    collector_type: 'html_list',
    config: { list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 1 },
    schedule: '0 6 * * *',
    rate_limit: 5,
    access_note: null,
  });
  expect(validate({ ...form, collectorType: 'search_query', config: { queries: 'x' } }, [{ name: 'queries', type: 'list', required: true, help: null }], undefined).errors.kind).toBe(
    FORM_COPY.originalSearch,
  );
  expect(validate({ ...form, schedule: 'daily', rateLimit: '0.5' }, HTML, undefined).errors).toMatchObject({ schedule: FORM_COPY.schedule, rateLimit: FORM_COPY.rateLimit });
});

test('detailText: a string, or FastAPI\'s list of errors', () => {
  expect(detailText('config: bad selector')).toBe('config: bad selector');
  expect(detailText([{ loc: ['body', 'config'], msg: 'selector does not parse' }, { loc: ['body', 'home_url'], msg: 'internal address' }])).toBe(
    'config: selector does not parse; home_url: internal address',
  );
  expect(detailText(undefined)).toBeNull();
});
