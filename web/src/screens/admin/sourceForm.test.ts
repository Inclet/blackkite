import { expect, test } from 'vitest';
import type { ConfigField, SourceDetail } from '../../api/sources';
import { collectorTypesFrom } from '../../api/sources';
import {
  buildConfig,
  configValues,
  detailText,
  emptyForm,
  fieldHint,
  fieldKind,
  fieldLabel,
  fieldsFor,
  fieldMessage,
  flattenFields,
  FORM_COPY,
  placeServerErrors,
  toForm,
  validate,
  WHOLE_CONFIG,
} from './sourceForm';
import { adminSource, COLLECTOR_TYPES } from './testData';

const TYPES = collectorTypesFrom(COLLECTOR_TYPES);
const HTML = fieldsFor(TYPES, 'html_list')!;
const SOURCE = adminSource() as unknown as SourceDetail;
const field = (name: string, kind: string, more: Partial<ConfigField> = {}): ConfigField => ({ name, kind, required: false, help: null, ...more });

test('the contract\'s field kinds map to inputs; object_list, map, json and unknown kinds are JSON', () => {
  expect(['string', 'url', 'integer', 'number', 'boolean', 'choice', 'string_list', 'selector', 'object', 'object_list', 'map', 'json', 'weird'].map(fieldKind)).toEqual([
    'text',
    'url',
    'integer',
    'number',
    'boolean',
    'choice',
    'list',
    'selector',
    'json',
    'json',
    'json',
    'json',
    'json',
  ]);
  expect(fieldLabel(field('selectors.item_title', 'string'))).toBe('Selectors: item title');
  expect(fieldLabel(field('x', 'string', { label: 'List page' }))).toBe('List page');
});

test('nested objects flatten to dotted names; a field inside an optional object is optional', () => {
  expect(HTML.map((f) => [f.name, f.kind, f.required])).toEqual([
    ['list_url', 'url', true],
    ['pagination_pattern', 'string', false],
    ['first_page', 'integer', false],
    ['max_pages', 'integer', false],
    ['selectors.item', 'string', true],
    ['selectors.title', 'selector', true],
    ['selectors.link', 'selector', false],
    ['selectors.date', 'selector', false],
    ['selectors.deadline', 'selector', false],
    ['selectors.organisation', 'selector', false],
    ['selectors.snippet', 'selector', false],
    ['detail.selectors.date', 'selector', false],
    ['detail.selectors.deadline', 'selector', false],
    ['detail.selectors.organisation', 'selector', false],
    ['detail.selectors.snippet', 'selector', false],
    ['detail.max_items', 'integer', false],
  ]);
  expect(flattenFields([field('a', 'object')])).toEqual([field('a', 'object')]);
});

test('hints: the API\'s help, defaults, ranges; string lists say commas; selectors explained once', () => {
  const html = (name: string) => HTML.find((f) => f.name === name)!;
  expect(fieldHint(html('max_pages'))).toBe('Pages to read per run, counting list_url as 1. Default: 1. From 1 to 20.');
  expect(fieldHint(fieldsFor(TYPES, 'search_query')![0]!)).toBe('Search queries, one request each per run. Separate with commas.');
  expect(fieldHint(field('queries', 'string_list', { help: 'Search queries, one per line.' }))).toBe('Search queries, separated by commas.');
  expect(fieldHint(fieldsFor(TYPES, 'search_query')![1]!)).toBe('Only keep results from these domains (site: filter). Separate with commas.');
  // The API's selector help already says "A CSS selector, or {css, attr}"; the editor does not repeat it.
  expect(fieldHint(html('selectors.title'))).toBe('Title inside the item. A CSS selector, or {css, attr} to read an attribute.');
  expect(fieldHint(field('title', 'selector', { help: 'Title.' }))).toBe('Title. A CSS selector, or JSON such as {"css": "a", "attr": "href"}.');
});

test('config to form and back: nesting, numbers, selectors as text or JSON, undescribed keys survive', () => {
  const stored = { ...SOURCE.config, selectors: { item: 'tr', title: { css: 'td a', attr: 'title' }, extra_key: 'kept' } };
  const values = configValues(HTML, stored);
  expect(values).toMatchObject({ list_url: 'https://www.umucyo.gov.rw/tenders', 'selectors.item': 'tr', 'selectors.title': '{"css":"td a","attr":"title"}', max_pages: '1', 'detail.max_items': '' });
  const { config, errors } = buildConfig(HTML, { ...values, max_pages: '3', 'selectors.link': 'a.more' }, stored);
  expect(errors).toEqual({});
  expect(config).toEqual({
    list_url: 'https://www.umucyo.gov.rw/tenders',
    selectors: { item: 'tr', title: { css: 'td a', attr: 'title' }, link: 'a.more', extra_key: 'kept' },
    max_pages: 3,
  });
  expect(buildConfig(HTML, { ...values, max_pages: '' }, stored).config).not.toHaveProperty('max_pages');
  // A nested optional block filled in creates its parents.
  expect(buildConfig(HTML, { ...values, 'detail.selectors.deadline': '.closing' }, {}).config.detail).toEqual({ selectors: { deadline: '.closing' } });
});

test('config errors: required, whole numbers, ranges, URLs, JSON, choices', () => {
  const { errors } = buildConfig(HTML, { list_url: 'umucyo', 'selectors.item': '', 'selectors.title': '{bad', max_pages: '30', 'detail.max_items': 'two' });
  expect(errors).toEqual({
    list_url: FORM_COPY.urlInvalid,
    'selectors.item': FORM_COPY.required,
    'selectors.title': FORM_COPY.json,
    max_pages: FORM_COPY.range(1, 20),
    'detail.max_items': FORM_COPY.integer,
  });
  const map = [field('params', 'map')];
  expect(buildConfig(map, { params: '{"country": "RW"}' }).config).toEqual({ params: { country: 'RW' } });
  expect(buildConfig(map, { params: '{x' }).errors).toEqual({ params: FORM_COPY.json });
  expect(buildConfig([field('queries', 'string_list', { required: true })], { queries: 'tender Kigali , transport,' }).config).toEqual({ queries: ['tender Kigali', 'transport'] });
  expect(buildConfig([field('strip', 'boolean')], { strip: true }).config).toEqual({ strip: true });
  const choice = [field('format', 'choice', { options: ['html', 'text'] })];
  expect(buildConfig(choice, { format: 'text' }).config).toEqual({ format: 'text' });
  expect(buildConfig(choice, { format: 'pdf' }).errors).toEqual({ format: FORM_COPY.choice(['html', 'text']) });
});

test('no field list: the whole config as one JSON object', () => {
  expect(configValues(null, { a: 1 })).toEqual({ [WHOLE_CONFIG]: '{"a":1}' });
  expect(buildConfig(null, { [WHOLE_CONFIG]: '{"a":2}' }).config).toEqual({ a: 2 });
  expect(buildConfig(null, { [WHOLE_CONFIG]: '[1]' }).errors).toEqual({ [WHOLE_CONFIG]: FORM_COPY.configObject });
  expect(buildConfig(null, {}).config).toEqual({});
});

test('validate: the record and the body the API takes (SourceIn, camelCase)', () => {
  const empty = validate(emptyForm(), null, undefined);
  expect(empty.body).toBeNull();
  expect(empty.errors).toMatchObject({ name: FORM_COPY.nameRequired, homeUrl: FORM_COPY.urlRequired, streams: FORM_COPY.streamsRequired, kind: FORM_COPY.kindRequired, collectorType: FORM_COPY.typeRequired });

  const form = toForm(SOURCE, TYPES);
  const ok = validate({ ...form, schedule: '0 6 * * *', accessNote: ' ' }, HTML, SOURCE.config);
  expect(ok.errors).toEqual({});
  expect(ok.body).toEqual({
    name: 'Umucyo e-procurement',
    homeUrl: 'https://www.umucyo.gov.rw/',
    publisher: 'RPPA',
    streams: ['tender'],
    kind: 'original',
    collectorType: 'html_list',
    config: { list_url: 'https://www.umucyo.gov.rw/tenders', selectors: { item: 'tr', title: 'td a', link: 'td a' }, max_pages: 1 },
    schedule: '0 6 * * *',
    rateLimit: 5,
    accessNote: null,
  });
  expect(validate({ ...form, collectorType: 'search_query', config: { queries: 'x' } }, [field('queries', 'string_list', { required: true })], undefined).errors.kind).toBe(FORM_COPY.originalSearch);
  expect(validate({ ...form, schedule: 'daily', rateLimit: '0.5' }, HTML, undefined).errors).toMatchObject({ schedule: FORM_COPY.schedule, rateLimit: FORM_COPY.rateLimit });
});

test('detailText: a string, or FastAPI\'s list of errors', () => {
  expect(detailText('config: bad selector')).toBe('config: bad selector');
  expect(detailText([{ loc: ['body', 'config'], msg: 'selector does not parse' }, { loc: ['body', 'homeUrl'], msg: 'internal address' }])).toBe(
    'config: selector does not parse; homeUrl: internal address',
  );
  expect(detailText(undefined)).toBeNull();
});

test('server field messages read as sentences', () => {
  expect(fieldMessage('address 127.0.0.1 is not public')).toBe('Address 127.0.0.1 is not public.');
  expect(fieldMessage('is required')).toBe('This is required.');
  expect(fieldMessage('must be at least 1.')).toBe('This must be at least 1.');
  expect(fieldMessage('  ')).toBe('');
});

test('server field errors land on their inputs; config paths on the field or its longest prefix; the rest are listed', () => {
  const SEARCH = fieldsFor(TYPES, 'search_query')!;
  expect(SEARCH.some((f) => f.name === 'queries')).toBe(true);
  const { placed, unplaced } = placeServerErrors(
    [
      { field: 'homeUrl', message: 'address 10.0.0.1 is not public' },
      { field: 'name', message: 'a source with that name already exists' },
      { field: 'config.queries.0', message: 'must not be empty' },
      { field: 'config.wat', message: 'is not a setting this accepts' },
      { field: 'suggestionId', message: 'not found' },
      { field: null, message: 'Too many problems' },
    ],
    SEARCH,
  );
  expect(placed).toEqual({
    homeUrl: 'Address 10.0.0.1 is not public.',
    name: 'A source with that name already exists.',
    config: { queries: 'This must not be empty.' },
  });
  expect(unplaced).toEqual(['Wat: is not a setting this accepts.', 'Suggestion id: not found.', 'Too many problems.']);

  const nested = placeServerErrors(
    [
      { field: 'config.selectors.item', message: "invalid CSS selector 'li['" },
      { field: 'config.selectors.item', message: 'second' },
    ],
    HTML,
  );
  expect(nested.placed.config).toEqual({ 'selectors.item': "Invalid CSS selector 'li['. Second." });
  expect(placeServerErrors([{ field: 'config.feed_url', message: 'is required' }], null).placed.config).toEqual({ [WHOLE_CONFIG]: 'This is required.' });
});
