// 백엔드 POST /v1/stt (Whisper) 호출 — 녹음 파일 → 문장 + 감지 언어
import { ChatApiError } from './chat';

export interface SttResult {
  text: string;
  language: string | null;                         // ko | en | zh ...
  duration?: number | null;
  route: 'korean' | 'foreign' | 'unsupported';
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '';
const TIMEOUT_MS = 60_000;   // CPU Whisper: 음성 10초 ≈ 5초 처리

export async function postStt(audio: Blob, filename: string, langHint?: string): Promise<SttResult> {
  const form = new FormData();
  form.append('audio', audio, filename);
  if (langHint) form.append('lang_hint', langHint);
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  let r: Response;
  try {
    r = await fetch(`${API_BASE}/v1/stt`, { method: 'POST', body: form, signal: ctrl.signal });
  } catch {
    throw new ChatApiError('NETWORK', '서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.');
  } finally {
    window.clearTimeout(timer);
  }
  const data = await r.json().catch(() => null);
  if (!r.ok) {
    throw new ChatApiError(data?.error_code ?? `HTTP_${r.status}`,
      data?.message ?? '음성을 인식하지 못했어요. 다시 말씀해 주세요.');
  }
  return data as SttResult;
}
