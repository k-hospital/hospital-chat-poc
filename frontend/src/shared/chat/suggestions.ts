// 입력창을 눌렀을 때 보여 주는 화면별 추천 질문.
// 목록은 엑셀(frontend/data/suggestions.xlsx)에서 편집하고 `npm run sync:suggestions`로 suggestions.json을 만든다.
// 키 = 화면(메인은 'home', 연결 페이지는 그 기능의 intent). 목록이 없는 화면은 메인 목록을 쓴다.
// 질문마다 연결 기능(intent)이 정해져 있어 누르면 그 기능으로 바로 이동한다 (키워드 판별기보다 우선).
import type { AnyIcon } from '../ui/icons';
import { AGENT_KEY, CALLBACK_KEY } from '../links/linkStore';
import { SYMPTOM_INTENT } from './intentRouter';
import data from './suggestions.json';

export const HOME_SCREEN = 'home';

export interface SuggestionDef {
  text: string;
  intent: string;
  label: string;
}

export const SUGGESTIONS: Record<string, SuggestionDef[]> = data.screens;

const ICONS: Record<string, AnyIcon> = {
  [SYMPTOM_INTENT]: 'stethoscope',
  'doctor.search': 'stethoscope',
  'info.directions': 'pin',
  'faq.parking': 'pin',
  'booking.start': 'calendar',
  'booking.lookup': 'calendar',
  'info.health': 'book',
  [AGENT_KEY]: 'headset',
  [CALLBACK_KEY]: 'phone',
};

export interface Suggestion extends SuggestionDef {
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

export function suggestionsFor(screen: string): SuggestionDef[] {
  return SUGGESTIONS[screen] ?? SUGGESTIONS[HOME_SCREEN] ?? [];
}

// 연결 주소가 없는 기능의 질문은 숨긴다 (누르면 "준비중"만 뜨는 헛걸음 방지)
export function visibleSuggestions(screen: string, isLinked: (intent: string) => boolean): Suggestion[] {
  return suggestionsFor(screen)
    .filter((s) => isLinked(s.intent))
    .map((s) => ({ ...s, icon: ICONS[s.intent] ?? 'clipboard' }));
}
