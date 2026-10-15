// 상담 운영시간 설정 — 이 시간 밖이면 메인 화면이 야간 화면(상담원 대신 콜백 안내)으로 바뀐다.
// POC 단계라 브라우저(localStorage)에만 저장한다. 저장한 적이 없으면(null) 서버가 알려 주는 운영시간을 쓴다.
export interface OperatingHours {
  start: string;         // 'HH:MM' (24시간)
  end: string;           // 'HH:MM' — 이 시각부터는 운영 시간이 아니다
  weekdaysOnly: boolean; // true 면 월~금만 운영, 주말은 야간 화면
}

// 서버의 기본 운영시간(평일 08:30 – 17:30)과 같다. 설정 화면의 초기 입력값으로 쓴다.
export const DEFAULT_HOURS: OperatingHours = { start: '08:30', end: '17:30', weekdaysOnly: true };

const STORAGE_KEY = 'chatpoc.hours.v1';

export const isValidTime = (v: string): boolean => /^([01]\d|2[0-3]):[0-5]\d$/.test(v);

const toMinutes = (v: string): number => Number(v.slice(0, 2)) * 60 + Number(v.slice(3));

// 입력값의 문제를 한 줄 문구로 돌려준다. 문제가 없으면 null
export function hoursError(h: OperatingHours): string | null {
  if (!isValidTime(h.start)) return '시작 시간을 24시간 형식(예: 08:30)으로 입력하세요';
  if (!isValidTime(h.end)) return '종료 시간을 24시간 형식(예: 17:30)으로 입력하세요';
  if (toMinutes(h.end) <= toMinutes(h.start)) return '종료 시간은 시작 시간보다 늦어야 합니다';
  return null;
}

// now 가 운영 시간 안인지 (시작 시각 포함, 종료 시각 제외). 시각은 이 기기의 현지 시간 기준
export function isWithinHours(h: OperatingHours, now: Date): boolean {
  if (h.weekdaysOnly) {
    const day = now.getDay(); // 0 일요일 … 6 토요일
    if (day === 0 || day === 6) return false;
  }
  const minutes = now.getHours() * 60 + now.getMinutes();
  return minutes >= toMinutes(h.start) && minutes < toMinutes(h.end);
}

export const hoursText = (h: OperatingHours): string =>
  `${h.weekdaysOnly ? '평일' : '매일'} ${h.start} – ${h.end}`;

export function loadHours(): OperatingHours | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return null;
    const p = JSON.parse(raw) as Partial<OperatingHours> | null;
    if (!p || typeof p.start !== 'string' || typeof p.end !== 'string') return null;
    const h: OperatingHours = { start: p.start, end: p.end, weekdaysOnly: p.weekdaysOnly !== false };
    return hoursError(h) === null ? h : null;
  } catch (err) {
    console.warn('운영시간 설정을 불러오지 못했습니다', err);
    return null;
  }
}

// null 을 저장하면 설정을 지워 서버 기준으로 되돌린다
export function saveHours(h: OperatingHours | null): boolean {
  try {
    if (h === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, JSON.stringify(h));
    return true;
  } catch (err) {
    console.warn('운영시간 설정을 저장하지 못했습니다', err);
    return false;
  }
}
