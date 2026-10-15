// 상담원 연결 (국내 전용) · 콜백 요청 API — backend/app.py 상담원 연결 구간과 짝
import { ChatApiError } from './chat';

const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export type HandoffReason = 'closed_hours' | 'no_agent' | null;
export interface HandoffStart {
  available: boolean;
  reason: HandoffReason;
  hours_text: string;
  ticket?: string;
  position?: number;
}
export interface HandoffMessage { from: 'user' | 'agent' | 'system'; text: string; ts: number }
export interface TranscriptLine { role: 'user' | 'bot'; text: string }

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try {
    r = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ChatApiError('NETWORK', '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ChatApiError(data?.error_code ?? `HTTP_${r.status}`, data?.message ?? '잠시 후 다시 시도해 주세요.');
  return data as T;
}

const json = (body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body),
});

export const startHandoff = (transcript: TranscriptLine[]) => call<HandoffStart>('/v1/handoff', json({ transcript }));

export const postCallback = (phone: string, preferredTime: string, note: string) =>
  call<{ ok: boolean; retention_days: number }>('/v1/callbacks',
    json({ phone, preferred_time: preferredTime, note, consent: true }));

// WebSocket 주소: API_BASE가 없으면 같은 사이트 (개발 중에는 Vite 프록시가 ws도 전달)
export function wsUrl(path: string): string {
  if (API_BASE) return API_BASE.replace(/^http/, 'ws') + path;
  return `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}${path}`;
}

// ---- 상담원 화면용
export interface Callback { id: number; created: number; phone: string; preferred_time: string; note: string }
const bearer = (token: string) => ({ Authorization: `Bearer ${token}` });
export const agentLogin = (password: string, name: string) =>
  call<{ token: string; name: string }>('/v1/agent/login', json({ password, name }));
export const listCallbacks = (token: string) =>
  call<{ items: Callback[] }>('/v1/agent/callbacks', { headers: bearer(token) });
export const doneCallback = (token: string, id: number) =>
  call<{ ok: boolean }>(`/v1/agent/callbacks/${id}/done`, { method: 'POST', headers: bearer(token) });

export const hhmm = (ts: number) =>
  new Date(ts * 1000).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' });
