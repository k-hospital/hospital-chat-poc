import { afterEach, describe, expect, it, vi } from 'vitest';
import { classifyWithServer, parseIntents } from './llmRouter';

afterEach(() => vi.unstubAllGlobals());

const okResponse = (body: unknown) => ({ ok: true, json: async () => body }) as Response;

describe('parseIntents', () => {
  it('기능 목록을 순서대로 읽고 주제가 있으면 함께 담는다', () => {
    expect(parseIntents({ intents: [
      { intent: 'faq.parking', label: '주차 안내', topic: null },
      { intent: 'info.directions', label: '오시는 길', topic: 'subway' },
    ] })).toEqual([
      { intent: 'faq.parking', label: '주차 안내' },
      { intent: 'info.directions', label: '오시는 길', topic: 'subway' },
    ]);
  });

  it('최대 3개까지만 쓴다', () => {
    const intents = ['a', 'b', 'c', 'd'].map((k) => ({ intent: k, label: k }));
    expect(parseIntents({ intents })).toHaveLength(3);
  });

  it.each([null, {}, { intents: 'faq.hours' }, { intents: [] }, { intents: [{ intent: 1, label: 2 }] }])(
    '형식이 다르면 null: %j', (data) => {
      expect(parseIntents(data)).toBeNull();
    },
  );
});

describe('classifyWithServer', () => {
  it('질문을 서버에 보내고 결과를 돌려준다 (주소에 질문을 넣지 않는다)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ intents: [{ intent: 'faq.hours', label: '진료 시간', topic: null }] }));
    vi.stubGlobal('fetch', fetchMock);

    const out = await classifyWithServer('점심시간에도 열어요', 'http://api.test');

    expect(out).toEqual([{ intent: 'faq.hours', label: '진료 시간' }]);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api.test/v1/chat/messages');
    expect(url).not.toContain('점심');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ text: '점심시간에도 열어요' });
  });

  it('서버가 오류(503 등)를 주면 null — 규칙으로 대체할 수 있게', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response));
    expect(await classifyWithServer('주차')).toBeNull();
  });

  it('네트워크 오류·시간 초과도 예외 없이 null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    expect(await classifyWithServer('주차')).toBeNull();
  });

  it('응답 형식이 다르면 null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(okResponse({ detail: 'x' })));
    expect(await classifyWithServer('주차')).toBeNull();
  });
});
