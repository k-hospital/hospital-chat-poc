// 직접 입력한 질문을 서버(POST /v1/chat/messages, 사내 LLM)로 분류한다.
// 서버가 없거나 느리거나 형식이 다르면 null — 호출하는 쪽이 키워드 규칙(routeQuestion)으로 대체한다.
// 응급 신호는 서버를 기다리지 않고 규칙이 먼저 처리하므로 여기서는 다루지 않는다(서버가 emergency 를 줄 수는 있음).

export interface RoutedIntent {
  intent: string;       // 기능 키 (예: 'faq.parking', 'emergency', 'unknown')
  label: string;        // 화면에 보여 줄 이름
  topic?: string;       // 오시는 길(subway/bus/car), 증상 안내(digestive/headache/respiratory)
}

const TIMEOUT_MS = 5000;
const MAX_ITEMS = 3;

export async function classifyWithServer(text: string, apiBase = ''): Promise<RoutedIntent[] | null> {
  try {
    const res = await fetch(`${apiBase}/v1/chat/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return parseIntents(await res.json());
  } catch {
    // 서버 없음·시간 초과·네트워크 오류는 모두 "규칙으로 대체" — 사용자에게 오류를 보이지 않는다
    return null;
  }
}

export function parseIntents(data: unknown): RoutedIntent[] | null {
  const list = (data as { intents?: unknown } | null)?.intents;
  if (!Array.isArray(list)) return null;
  const items: RoutedIntent[] = [];
  for (const it of list) {
    const o = it as { intent?: unknown; label?: unknown; topic?: unknown };
    if (typeof o?.intent !== 'string' || typeof o.label !== 'string') continue;
    items.push(typeof o.topic === 'string' && o.topic ? { intent: o.intent, label: o.label, topic: o.topic }
      : { intent: o.intent, label: o.label });
  }
  return items.length > 0 ? items.slice(0, MAX_ITEMS) : null;
}
