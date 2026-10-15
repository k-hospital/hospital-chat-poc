// 백엔드 POST /v1/chat (한국어·외국어 통합 답변) 호출
// 응답 형식은 backend/app.py의 _answer_korean / _answer_foreign과 같다.

export interface ChatSource {
  title: string;
  category?: string | null;
  source_url?: string | null;
  score?: number;
}

export interface ChatResponse {
  lang: string;                      // ko | en | zh
  answer: string;
  sources: ChatSource[];
  emergency: string | null;          // 응급 표현이 있으면 안내 문구
  disclaimer: string;
  translated_notice: string | null;  // 외국어 답변일 때만
  query_ko?: string;
}

export class ChatApiError extends Error {
  constructor(public code: string, message: string) {
    super(message);
  }
}

// 배포 시 VITE_API_BASE로 백엔드 주소 지정 (비우면 같은 도메인의 /v1 — 개발 중에는 Vite 프록시)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const TIMEOUT_MS = 60_000;   // LLM 답변이 길면 10초 이상 걸릴 수 있다

export async function postChat(message: string, lang?: string): Promise<ChatResponse> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let r: Response;
  try {
    r = await fetch(`${API_BASE}/v1/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(lang ? { message, lang } : { message }),
      signal: ctrl.signal,
    });
  } catch {
    throw new ChatApiError('NETWORK', '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
  } finally {
    window.clearTimeout(timer);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    throw new ChatApiError(data?.error_code ?? `HTTP_${r.status}`,
      data?.message ?? '잠시 서비스를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.');
  }
  return data as ChatResponse;
}
