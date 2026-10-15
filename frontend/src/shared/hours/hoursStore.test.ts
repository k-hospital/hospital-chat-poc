import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_HOURS, hoursError, hoursText, isValidTime, isWithinHours, loadHours, saveHours, type OperatingHours,
} from './hoursStore';

const STORAGE_KEY = 'chatpoc.hours.v1';
const weekdays: OperatingHours = { start: '08:30', end: '17:30', weekdaysOnly: true };
const daily: OperatingHours = { ...weekdays, weekdaysOnly: false };

// 2026-10-15 은 목요일, 10-17 은 토요일, 10-18 은 일요일
const at = (day: number, hh: number, mm: number) => new Date(2026, 9, day, hh, mm);

function stubStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => { data.set(k, v); },
    removeItem: (k: string) => { data.delete(k); },
  });
  return data;
}

describe('isWithinHours', () => {
  it('시작 시각부터 종료 시각 직전까지만 운영 시간이다', () => {
    expect(isWithinHours(weekdays, at(15, 8, 29))).toBe(false);
    expect(isWithinHours(weekdays, at(15, 8, 30))).toBe(true);
    expect(isWithinHours(weekdays, at(15, 12, 0))).toBe(true);
    expect(isWithinHours(weekdays, at(15, 17, 29))).toBe(true);
    expect(isWithinHours(weekdays, at(15, 17, 30))).toBe(false);
  });

  it('평일만 운영이면 주말은 시간이 맞아도 야간이다', () => {
    expect(isWithinHours(weekdays, at(17, 10, 0))).toBe(false);
    expect(isWithinHours(weekdays, at(18, 10, 0))).toBe(false);
  });

  it('매일 운영이면 주말에도 시간만 본다', () => {
    expect(isWithinHours(daily, at(17, 10, 0))).toBe(true);
    expect(isWithinHours(daily, at(18, 20, 0))).toBe(false);
  });
});

describe('hoursText / validation', () => {
  it('안내 문구를 만든다', () => {
    expect(hoursText(weekdays)).toBe('평일 08:30 – 17:30');
    expect(hoursText(daily)).toBe('매일 08:30 – 17:30');
  });

  it('기본값은 서버와 같은 평일 08:30 – 17:30', () => {
    expect(DEFAULT_HOURS).toEqual(weekdays);
  });

  it.each(['08:30', '00:00', '23:59'])('올바른 시각: %s', (v) => expect(isValidTime(v)).toBe(true));
  it.each(['8:30', '24:00', '12:60', '', '08-30', 'abc'])('올바르지 않은 시각: %s', (v) => expect(isValidTime(v)).toBe(false));

  it('종료가 시작보다 늦어야 한다', () => {
    expect(hoursError(weekdays)).toBeNull();
    expect(hoursError({ ...weekdays, end: '08:30' })).toMatch(/종료/);
    expect(hoursError({ ...weekdays, end: '07:00' })).toMatch(/종료/);
    expect(hoursError({ ...weekdays, start: '25:00' })).toMatch(/시작/);
  });
});

describe('loadHours / saveHours', () => {
  beforeEach(() => { vi.unstubAllGlobals(); });

  it('저장한 적이 없으면 null (서버 기준 사용)', () => {
    stubStorage();
    expect(loadHours()).toBeNull();
  });

  it('저장한 값을 다시 읽는다', () => {
    stubStorage();
    expect(saveHours({ start: '09:00', end: '18:00', weekdaysOnly: false })).toBe(true);
    expect(loadHours()).toEqual({ start: '09:00', end: '18:00', weekdaysOnly: false });
  });

  it('null 을 저장하면 설정이 지워져 서버 기준으로 돌아간다', () => {
    stubStorage();
    saveHours(weekdays);
    expect(saveHours(null)).toBe(true);
    expect(loadHours()).toBeNull();
  });

  it('깨진 값은 무시한다', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    stubStorage({ [STORAGE_KEY]: '{not json' });
    expect(loadHours()).toBeNull();
    stubStorage({ [STORAGE_KEY]: JSON.stringify({ start: '99:99', end: '17:30', weekdaysOnly: true }) });
    expect(loadHours()).toBeNull();
    stubStorage({ [STORAGE_KEY]: JSON.stringify({ start: '10:00', end: '09:00', weekdaysOnly: true }) });
    expect(loadHours()).toBeNull();
  });

  it('저장소가 막혀 있어도 오류 없이 동작한다', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
      removeItem: () => { throw new Error('blocked'); },
    });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(loadHours()).toBeNull();
    expect(saveHours(weekdays)).toBe(false);
  });
});
