// 기능별 연결 주소 저장소 — 키는 메뉴의 intent, 상담 버튼은 아래 고정 키 사용
// POC 단계라 브라우저(localStorage)에만 저장. 백엔드 API가 생기면 load/save만 교체.
export const AGENT_KEY = 'action.agent';
export const CALLBACK_KEY = 'action.callback';

export type LinkMap = Record<string, string>;

const STORAGE_KEY = 'chatpoc.links.v1';

// 처음 여는 브라우저(저장된 설정 없음)에 적용되는 기본 연결 주소.
// 한 번이라도 설정을 저장하면 저장한 값이 우선한다 (기본값을 지운 것도 유지).
// 연결 페이지는 챗봇(<사이트 경로>/chat/)과 같은 사이트의 /pages/ 아래에 있다.
// 사이트가 하위 경로(예: GitHub Pages /hospital-chat-poc/)에 올라가도 맞도록 빌드된 base에서 사이트 경로를 구한다.
// 개발 서버·테스트에서는 BASE_URL이 '/'라서 그대로 '/pages/...'가 된다.
const SITE_ROOT = import.meta.env.BASE_URL.replace(/chat\/$/, '');

export const DEFAULT_LINKS: LinkMap = {
  'info.directions': `${SITE_ROOT}pages/directions.html`,
  'symptom.guide': `${SITE_ROOT}pages/symptom.html`,
  'info.health': `${SITE_ROOT}pages/health-checkup.html`,
  // 주차 안내는 오시는 길의 자가용 탭(주차 안내 포함)으로 연결
  'faq.parking': `${SITE_ROOT}pages/directions.html#car`,
};

export function loadLinks(): LinkMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return { ...DEFAULT_LINKS };
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        (e): e is [string, string] => typeof e[1] === 'string' && e[1].trim() !== '',
      ),
    );
  } catch (err) {
    console.warn('연결 주소를 불러오지 못했습니다', err);
    return { ...DEFAULT_LINKS };
  }
}

export function saveLinks(links: LinkMap): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(links));
    return true;
  } catch (err) {
    console.warn('연결 주소를 저장하지 못했습니다', err);
    return false;
  }
}

// http(s) 주소 또는 같은 사이트 경로(/pages/...)만 허용 (javascript: 등 차단)
export function isValidUrl(value: string): boolean {
  if (/^\/(?!\/)\S*$/.test(value)) return true;
  try {
    const u = new URL(value);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}
