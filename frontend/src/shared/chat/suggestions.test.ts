import { describe, expect, it } from 'vitest';
import { routeQuestion } from './intentRouter';
import { matchesQuery, SUGGESTIONS, suggestionsFor, visibleSuggestions } from './suggestions';

describe('suggestions', () => {
  // 목록의 질문은 누르면 바로 전송되므로, 하나라도 판별에 실패하면 헛걸음이 된다
  it.each(Object.entries(SUGGESTIONS).flatMap(([screen, list]) => list.map((q) => [screen, q])))(
    '[%s] "%s" 는 판별에 성공하고 응급으로 분류되지 않음', (_screen, q) => {
      expect(routeQuestion(q).kind).toBe('intent');
    },
  );

  it('목록이 없는 화면은 메인 화면 목록을 사용', () => {
    expect(suggestionsFor('faq.hours')).toEqual(SUGGESTIONS.home);
    expect(suggestionsFor('info.directions')).not.toEqual(SUGGESTIONS.home);
  });

  it('연결 주소가 없는 기능의 질문은 숨김', () => {
    const onlyDirections = (intent: string) => intent === 'info.directions';
    const shown = visibleSuggestions('home', onlyDirections);
    expect(shown.length).toBeGreaterThan(0);
    expect(shown.every((s) => s.intent === 'info.directions')).toBe(true);
  });

  it('입력 중 걸러 보기: 띄어쓰기 무시, 글자가 순서대로 들어 있으면 일치', () => {
    expect(matchesQuery('배가 아파요', '배아파')).toBe(true);
    expect(matchesQuery('주차 되나요?', '주차')).toBe(true);
    expect(matchesQuery('병원 어떻게 가요?', '어떻게 가')).toBe(true);
    expect(matchesQuery('배가 아파요', '')).toBe(true);
    expect(matchesQuery('배가 아파요', '아파배')).toBe(false);
    expect(matchesQuery('머리가 아파요', '배')).toBe(false);
  });

  it('화면 안에서 같은 질문이 중복되지 않음', () => {
    for (const list of Object.values(SUGGESTIONS)) expect(new Set(list).size).toBe(list.length);
  });
});
