// 입력창을 눌렀을 때 보여 주는 화면별 추천 질문.
// 키 = 화면(메인은 'home', 연결 페이지는 그 기능의 intent). 목록이 없는 화면은 메인 목록을 쓴다.
// 목록의 질문은 누르면 바로 전송되므로 모두 판별에 성공해야 한다 (suggestions.test.ts가 보장).
import type { AnyIcon } from '../ui/icons';
import { routeQuestion, SYMPTOM_INTENT } from './intentRouter';

export const HOME_SCREEN = 'home';

export const SUGGESTIONS: Record<string, string[]> = {
  [HOME_SCREEN]: [
    '배가 아파요',
    '머리가 아파요',
    '기침이 나요',
    '병원 어떻게 가요?',
    '주차 되나요?',
    '진료 시간 알려주세요',
    '진료 예약하고 싶어요',
  ],
  'info.directions': [
    '지하철로 가는 방법',
    '버스 노선 알려주세요',
    '자가용으로 가는 방법',
    '주차 되나요?',
  ],
  [SYMPTOM_INTENT]: [
    '속이 쓰려요',
    '머리가 아파요',
    '기침이 나요',
    '진료 예약하고 싶어요',
    '의료진 찾아줘',
    '응급실 위치 알려줘',
  ],
};

const ICONS: Record<string, AnyIcon> = {
  [SYMPTOM_INTENT]: 'stethoscope',
  'doctor.search': 'stethoscope',
  'info.directions': 'pin',
  'faq.parking': 'pin',
  'booking.start': 'calendar',
  'booking.lookup': 'calendar',
  'info.health': 'book',
};

export interface Suggestion {
  text: string;
  intent: string;
  icon: AnyIcon;
}

// 입력 중 걸러 보기: 띄어쓰기를 무시하고, 입력한 글자가 순서대로 들어 있으면 일치
// ("배아파" → "배가 아파요", "주차" → "주차 되나요?")
export function matchesQuery(text: string, query: string): boolean {
  const q = query.replace(/\s+/g, '');
  if (!q) return true;
  const t = text.replace(/\s+/g, '');
  let i = 0;
  for (const ch of t) if (ch === q[i] && ++i === q.length) return true;
  return false;
}

export function suggestionsFor(screen: string): string[] {
  return SUGGESTIONS[screen] ?? SUGGESTIONS[HOME_SCREEN];
}

// 연결 주소가 없는 기능의 질문은 숨긴다 (누르면 "준비중"만 뜨는 헛걸음 방지)
export function visibleSuggestions(screen: string, isLinked: (intent: string) => boolean): Suggestion[] {
  return suggestionsFor(screen).flatMap((text) => {
    const r = routeQuestion(text);
    if (r.kind !== 'intent' || !isLinked(r.intent)) return [];
    return [{ text, intent: r.intent, icon: ICONS[r.intent] ?? 'clipboard' }];
  });
}
