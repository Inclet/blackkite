/**
 * What the web app sends matches the API's request models (tests/contract:
 * api-schemas.json is dumped from the API's Pydantic models).
 */
import { expect, test } from 'vitest';
import dump from '../../tests/contract/api-schemas.json';
import { check, type Schema } from '../../tests/contract/schemaCheck';
import { toForm, toInput } from '../screens/profiles/profileForm';
import type { Profile } from './types';

const schemas = dump.schemas as unknown as Record<string, Schema>;
const fits = (value: unknown, model: string) => check(value, schemas[model]!);

const IRONJI: Profile = {
  id: 'p1',
  name: 'Ironji-Trade',
  type: 'business',
  version: 1,
  active: true,
  data: {
    streams: ['tender', 'funding', 'event'],
    location: 'Kigali, Rwanda',
    sectors: ['logistics'],
    services: ['dry freight', 'cold chain'],
    capacity: { model: 'partner network', trucksInNetwork: 1000, refrigeratedInNetwork: 100, ownedTrucks: null, tonnage: { min: 10, max: 30 } },
    minContractRwf: 5000000,
  },
};

function sendable(body: ReturnType<typeof toInput>) {
  expect(fits(body, 'ProfileIn')).toEqual([]);
  expect(fits(body.data, body.type === 'business' ? 'BusinessData' : 'PersonalData')).toEqual([]);
}

test('a business profile from the editor fits ProfileIn and BusinessData', () => {
  sendable(toInput(toForm(IRONJI, 'business'), IRONJI.data));
  sendable(toInput({ ...toForm(IRONJI, 'business'), tonnageMin: '12.5', tonnageMax: '12.5' }, IRONJI.data));
});

test('a new personal profile fits PersonalData', () => {
  sendable(toInput({ ...toForm(null, 'personal'), name: 'Personal', instruments: ['RSE shares'], ticketMin: '100000' }));
});

test('a change of type sends only the new type\'s keys', () => {
  sendable(toInput({ ...toForm(IRONJI, 'business'), type: 'personal' }, IRONJI.data));
  const personal = { streams: ['investment' as const], horizon: '5 years', budgetRwf: 200000 };
  sendable(toInput({ ...toForm({ name: 'P', type: 'personal', active: true, data: personal }, 'personal'), type: 'business' }, personal));
});

test('the digest settings body fits DigestSettingsIn', () => {
  expect(fits({ channel: 'email', frequency: 'weekly', day: 'mon', alertThreshold: 75, streams: null }, 'DigestSettingsIn')).toEqual([]);
  expect(fits({ channel: 'email', address: 'x@y.rw', frequency: 'weekly', day: 'mon', alertThreshold: null, streams: null }, 'DigestSettingsIn')).toEqual([
    "$.address: not in the API's DigestSettingsIn",
  ]);
});
