import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_LINKS, loadLinks, saveLinks } from './linkStore';

const STORAGE_KEY = 'chatpoc.links.v1';

// 브라우저 localStorage 대용 (테스트는 node 환경)
function stubStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => { data.set(k, v); },
    removeItem: (k: string) => { data.delete(k); },
  });
  return data;
}

describe('loadLinks', () => {
  beforeEach(() => { vi.unstubAllGlobals(); });

  it('저장된 설정이 없으면 기본 주소를 모두 쓴다 (건강검진 안내 포함)', () => {
    stubStorage();
    const links = loadLinks();
    expect(links).toEqual(DEFAULT_LINKS);
    expect(links['info.health']).toMatch(/pages\/health-checkup\.html$/);
  });

  it('예전에 설정을 저장한 브라우저에도 새 기본 주소(건강검진 안내)가 한 번 들어온다', () => {
    const data = stubStorage({
      [STORAGE_KEY]: JSON.stringify({ 'info.directions': '/pages/directions.html', 'symptom.guide': '/pages/symptom.html' }),
    });
    const links = loadLinks();
    expect(links['info.health']).toBe(DEFAULT_LINKS['info.health']);
    // 기존에 저장해 둔 값은 그대로
    expect(links['info.directions']).toBe('/pages/directions.html');
    // 기존에 비워 둔 기본 연결(주차 안내)은 다시 채우지 않는다
    expect(links['faq.parking']).toBeUndefined();
    // 병합 결과가 저장되어 다음 로드에도 유지된다
    expect(JSON.parse(data.get(STORAGE_KEY)!)['info.health']).toBe(DEFAULT_LINKS['info.health']);
  });

  it('사용자가 건강검진 안내 주소를 지우면 다시 로드해도 비어 있다', () => {
    stubStorage({ [STORAGE_KEY]: JSON.stringify({ 'info.directions': '/pages/directions.html' }) });
    const first = loadLinks();
    expect(first['info.health']).toBeDefined();

    const { 'info.health': _removed, ...cleared } = first;
    expect(saveLinks(cleared)).toBe(true);

    expect(loadLinks()['info.health']).toBeUndefined();
  });

  it('사용자가 바꾼 주소는 기본값으로 덮어쓰지 않는다', () => {
    stubStorage({ [STORAGE_KEY]: JSON.stringify({ 'info.health': 'https://example.org/checkup' }) });
    expect(loadLinks()['info.health']).toBe('https://example.org/checkup');
  });

  it('저장소가 막혀 있어도 기본 주소로 동작한다', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => { throw new Error('blocked'); },
      setItem: () => { throw new Error('blocked'); },
    });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect(loadLinks()).toEqual(DEFAULT_LINKS);
  });
});
