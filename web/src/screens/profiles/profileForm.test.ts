import { expect, test } from 'vitest';
import type { Profile } from '../../api/types';
import { chipOptions, DATA_KEYS, DEFAULT_STREAMS, ERRORS, parseList, parseNumber, parseTonnage, toForm, toInput, validate } from './profileForm';

/** Spec 7.1's Ironji-Trade, camelCase. */
const IRONJI: Profile = {
  id: 'p1',
  name: 'Ironji-Trade',
  type: 'business',
  version: 3,
  active: true,
  data: {
    streams: ['tender', 'funding', 'event'],
    location: 'Kigali, Rwanda',
    services: ['dry freight', 'cold chain', 'last-mile distribution'],
    registrationsHeld: ['RDB company registration', 'RRA tax clearance', 'RSSB clearance'],
    registrationsNotHeld: ['Umucyo supplier account', 'transport operator licence'],
    capacity: { model: 'partner network', trucksInNetwork: 1000, refrigeratedInNetwork: 100, ownedTrucks: null, tonnage: null },
    minContractRwf: 5000000,
  },
};

test('a profile round-trips through the form unchanged', () => {
  const input = toInput(toForm(IRONJI, 'business'), IRONJI.data);
  expect(input.name).toBe('Ironji-Trade');
  expect(input.type).toBe('business');
  expect(input.data).toMatchObject(IRONJI.data);
  expect(input.data.exclusions).toEqual({ organisations: [], sectors: [], keywords: [] });
});

test('keys the form does not show are kept', () => {
  const withExtra = { ...IRONJI, data: { ...IRONJI.data, sectors: ['logistics'] } as Profile['data'] };
  expect(toInput(toForm(withExtra, 'business'), withExtra.data).data).toMatchObject({ sectors: ['logistics'] });
});

test('a new profile starts with its type\'s streams (spec 7.1) and nothing else', () => {
  expect(toForm(null, 'business').streams).toEqual(DEFAULT_STREAMS.business);
  expect(toForm(null, 'personal').streams).toEqual(['investment', 'event']);
  expect(toForm(null, 'personal').type).toBe('personal');
});

test('empty answers are null (not provided), never an empty filter', () => {
  const f = { ...toForm(null, 'business'), name: 'AI lab', services: ' , ', minContractRwf: '' };
  const d = toInput(f).data;
  expect(d.services).toBeNull();
  expect(d.registrationsHeld).toBeNull();
  expect(d.minContractRwf).toBeNull();
  expect(d.capacity?.ownedTrucks).toBeNull();
});

test('lists split on commas and new lines, trimmed and de-duplicated', () => {
  expect(parseList('software development, AI/ML,\n data , data')).toEqual(['software development', 'AI/ML', 'data']);
  expect(parseList('')).toBeNull();
});

test('numbers accept thousands separators and refuse words', () => {
  expect(parseNumber('5,000,000')).toBe(5000000);
  expect(parseNumber(' 1 000 ')).toBe(1000);
  expect(parseNumber('')).toBeNull();
  expect(parseNumber('about a hundred')).toBeNaN();
  expect(parseNumber('-3')).toBeNaN();
});

test('validation: name, at least one stream, numbers in the board\'s wording', () => {
  const f = { ...toForm(IRONJI, 'business'), name: ' ', streams: [], refrigeratedInNetwork: 'about a hundred', minContractRwf: 'five million' };
  expect(validate(f)).toEqual({ name: ERRORS.name, streams: ERRORS.streams, refrigeratedInNetwork: ERRORS.number, minContractRwf: ERRORS.rwf });
  expect(validate(toForm(IRONJI, 'business'))).toEqual({});
});

test('personal: instruments and topics from chips, ticket range checked', () => {
  const f = { ...toForm(null, 'personal'), name: 'Personal', instruments: ['RSE shares'], eventTopics: ['AI and tech'], ticketMin: '500,000', ticketMax: '100' };
  expect(validate(f)).toEqual({ ticketMax: ERRORS.ticketOrder });
  const d = toInput({ ...f, ticketMax: '' }).data;
  expect(d).toMatchObject({ instruments: ['RSE shares'], eventTopics: ['AI and tech'], ticketRangeRwf: { min: 500000, max: null }, streams: ['investment', 'event'] });
  expect(d.services).toBeUndefined();
});

test('streams are sent in stream order', () => {
  expect(toInput({ ...toForm(null, 'business'), name: 'x', streams: ['event', 'tender'] }).data.streams).toEqual(['tender', 'event']);
});

test('chip options: the spec set, then anything else already held', () => {
  expect(chipOptions(['a', 'b'], ['b', 'c'])).toEqual(['a', 'b', 'c']);
});

test('a change of type sends only keys valid for the new type (the API refuses the rest)', () => {
  const asPersonal = { ...toForm(IRONJI, 'business'), type: 'personal' as const, instruments: ['RSE shares'] };
  const d = toInput(asPersonal, { ...IRONJI.data, sectors: ['logistics'], locations: ['Musanze'] }).data;
  for (const k of Object.keys(d)) expect(DATA_KEYS.personal).toContain(k);
  expect(d).toMatchObject({ streams: ['tender', 'funding', 'event'], location: 'Kigali, Rwanda', locations: ['Musanze'], instruments: ['RSE shares'] });
  for (const k of ['services', 'sectors', 'capacity', 'registrationsHeld', 'registrationsNotHeld', 'minContractRwf']) expect(d).not.toHaveProperty(k);

  const personal = { streams: ['investment' as const], horizon: '5 years', availability: 'evenings', budgetRwf: 200000, ticketRangeRwf: { min: 1, max: 2 } };
  const b = toInput({ ...toForm({ name: 'P', type: 'personal', active: true, data: personal }, 'personal'), type: 'business' }, personal).data;
  for (const k of Object.keys(b)) expect(DATA_KEYS.business).toContain(k);
  for (const k of ['horizon', 'availability', 'budgetRwf', 'ticketRangeRwf', 'instruments', 'eventTopics']) expect(b).not.toHaveProperty(k);
});

test('same type: extra keys the API accepts are kept (business sectors and locations; personal horizon, availability, budget)', () => {
  const extra = { streams: ['investment' as const, 'event' as const], horizon: '5 years', availability: 'evenings', budgetRwf: 200000, locations: ['Kigali'] };
  const d = toInput(toForm({ name: 'P', type: 'personal', active: true, data: extra }, 'personal'), extra).data;
  expect(d).toMatchObject(extra);
  const biz = { ...IRONJI.data, sectors: ['logistics'], locations: ['Kigali', 'Rubavu'] };
  expect(toInput(toForm({ ...IRONJI, data: biz }, 'business'), biz).data).toMatchObject({ sectors: ['logistics'], locations: ['Kigali', 'Rubavu'] });
});

test('tonnage: one figure or a range, as the API takes it (float | {min, max})', () => {
  expect(parseTonnage('', '')).toBeNull();
  expect(parseTonnage('12.5', '12.5')).toBe(12.5);
  expect(parseTonnage('10', '30')).toEqual({ min: 10, max: 30 });
  expect(parseTonnage('10', '')).toEqual({ min: 10, max: null });
  expect(parseTonnage('', '30')).toEqual({ min: null, max: 30 });

  const one = { ...IRONJI, data: { ...IRONJI.data, capacity: { tonnage: 12.5 } } };
  expect(toForm(one, 'business')).toMatchObject({ tonnageMin: '12.5', tonnageMax: '12.5' });
  expect(toInput(toForm(one, 'business'), one.data).data.capacity?.tonnage).toBe(12.5);
  const range = { ...IRONJI, data: { ...IRONJI.data, capacity: { tonnage: { min: 10, max: null } } } };
  expect(toForm(range, 'business')).toMatchObject({ tonnageMin: '10', tonnageMax: '' });
  expect(toInput(toForm(range, 'business'), range.data).data.capacity?.tonnage).toEqual({ min: 10, max: null });
});

test('tonnage validation: whole tonnes for a range, largest not below smallest', () => {
  const f = toForm(IRONJI, 'business');
  expect(validate({ ...f, tonnageMin: '2.5', tonnageMax: '10' })).toEqual({ tonnageMin: ERRORS.tonnageWhole });
  expect(validate({ ...f, tonnageMin: '20', tonnageMax: '10' })).toEqual({ tonnageMax: ERRORS.tonnageOrder });
  expect(validate({ ...f, tonnageMin: 'lots', tonnageMax: '' })).toEqual({ tonnageMin: ERRORS.number });
  expect(validate({ ...f, tonnageMin: '2.5', tonnageMax: '2.5' })).toEqual({});
});
