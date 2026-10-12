import { describe, expect, it } from 'vitest';
import { mockConfig } from '../../features/home/mockConfig';
import { AGENT_KEY, CALLBACK_KEY } from '../links/linkStore';
import { QUESTION_TARGETS, routeQuestion, routeSuggestion } from './intentRouter';
import { HOME_SCREEN, matchesQuery, screenSuggestions, SUGGESTIONS, suggestionsFor } from './suggestions';

// 챗봇이 연결 주소를 받을 수 있는 기능 키 — 엑셀 '목록' 시트의 내부 키가 오타 나면 여기서 걸린다
const KNOWN_INTENTS = new Set([
  mockConfig.hero.intent,
  ...mockConfig.tiles.map((m) => m.intent),
  ...mockConfig.faqs.map((m) => m.intent),
  ...QUESTION_TARGETS.map((t) => t.intent),
  AGENT_KEY,
  CALLBACK_KEY,
]);

const ALL = Object.entries(SUGGESTIONS).flatMap(([screen, list]) => list.map((s) => [screen, s] as const));

describe('suggestions (엑셀에서 만든 목록)', () => {
  it('메인(home) 목록이 있어야 다른 화면의 대체 목록으로 쓸 수 있음', () => {
    expect(SUGGESTIONS[HOME_SCREEN]?.length).toBeGreaterThan(0);
  });

  it.each(ALL.map(([screen, s]) => [screen, s.text, s.intent]))(
    '[%s] "%s" → %s : 챗봇이 아는 기능이고 응급으로 분류되지 않음', (_screen, text, intent) => {
      expect(KNOWN_INTENTS.has(intent)).toBe(true);
      expect(routeQuestion(text).kind).not.toBe('emergency');
    },
  );

  it('목록이 없는 화면은 메인 화면 목록을 사용', () => {
    expect(suggestionsFor('faq.hours')).toEqual(SUGGESTIONS[HOME_SCREEN]);
  });

  it('연결 주소가 있든 없든 엑셀에서 사용으로 둔 질문을 모두 보여 주고, 정해 둔 기능을 그대로 가짐', () => {
    const shown = screenSuggestions(HOME_SCREEN);
    expect(shown.map((s) => s.text)).toEqual(SUGGESTIONS[HOME_SCREEN].map((s) => s.text));
    expect(shown.map((s) => s.intent)).toEqual(SUGGESTIONS[HOME_SCREEN].map((s) => s.intent));
    expect(shown.every((s) => Boolean(s.icon))).toBe(true);
  });

  it('화면 안에서 같은 질문이 중복되지 않음', () => {
    for (const list of Object.values(SUGGESTIONS)) {
      expect(new Set(list.map((s) => s.text.replace(/\s+/g, ''))).size).toBe(list.length);
    }
  });

  it('입력 중 걸러 보기: 띄어쓰기 무시, 글자가 순서대로 들어 있으면 일치', () => {
    expect(matchesQuery('배가 아파요', '배아파')).toBe(true);
    expect(matchesQuery('주차 되나요?', '주차')).toBe(true);
    expect(matchesQuery('병원 어떻게 가요?', '어떻게 가')).toBe(true);
    expect(matchesQuery('배가 아파요', '')).toBe(true);
    expect(matchesQuery('배가 아파요', '아파배')).toBe(false);
    expect(matchesQuery('머리가 아파요', '배')).toBe(false);
  });
});

describe('routeSuggestion (추천 질문을 눌렀을 때)', () => {
  it('키워드 판별기가 모르는 질문도 엑셀에서 정한 기능으로 이동 (상담원연결)', () => {
    expect(routeQuestion('상담원연결').kind).toBe('unknown');
    const r = routeSuggestion('상담원연결', AGENT_KEY, '상담원 연결');
    expect(r).toMatchObject({ kind: 'intent', intent: AGENT_KEY, label: '상담원 연결' });
  });

  it('판별기도 같은 기능으로 보면 주제(topic)와 안내 문구를 그대로 사용', () => {
    const r = routeSuggestion('지하철로 가는 방법', 'info.directions', '오시는 길');
    expect(r).toMatchObject({ kind: 'intent', intent: 'info.directions', topic: 'subway' });
  });

  it('판별기가 다른 기능으로 보더라도 엑셀에서 정한 기능이 우선 (주제는 가져오지 않음)', () => {
    const r = routeSuggestion('주차 되나요?', 'info.directions', '오시는 길');
    expect(r).toMatchObject({ kind: 'intent', intent: 'info.directions', label: '오시는 길' });
    expect(r.kind === 'intent' && r.topic).toBeFalsy();
  });

  it('응급 신호가 있으면 정해 둔 기능과 상관없이 응급 안내가 먼저', () => {
    expect(routeSuggestion('가슴이 아파요', 'info.directions', '오시는 길')).toEqual({ kind: 'emergency' });
  });
});
