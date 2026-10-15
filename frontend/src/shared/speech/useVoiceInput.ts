import { useCallback, useEffect, useRef, useState } from 'react';
import { ChatApiError } from '../api/chat';
import { postStt } from '../api/stt';

export type VoiceState = 'idle' | 'recording' | 'processing';

// 브라우저가 지원하는 녹음 형식 (Chrome·Edge: webm/opus, Safari: mp4)
const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
const pickMime = () =>
  MIME_CANDIDATES.find((m) => typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) ?? '';
const extOf = (mime: string) => (mime.includes('mp4') ? 'm4a' : mime.includes('ogg') ? 'ogg' : 'webm');

export const voiceSupported = () =>
  typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== 'undefined';

// 마이크 녹음 → /v1/stt → onResult(문장, 언어). 사내 Whisper 사용 (브라우저 Web Speech API는 음성이 외부로 나가므로 쓰지 않음)
// 버튼을 한 번 누르면 녹음, 다시 누르면 인식. maxSeconds가 지나면 자동으로 멈추고 인식한다.
export function useVoiceInput({ onResult, onError, maxSeconds = 30 }: {
  onResult: (text: string, lang: string | null) => void;
  onError: (message: string) => void;
  maxSeconds?: number;
}) {
  const [state, setState] = useState<VoiceState>('idle');
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<number | null>(null);
  const cancelled = useRef(false);

  const cleanup = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((t) => t.stop());   // 마이크 사용 표시 끄기
    stream.current = null;
    recorder.current = null;
  }, []);

  const stop = useCallback(() => {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    if (!window.isSecureContext) {
      onError('음성 입력은 https 주소(또는 localhost)에서만 쓸 수 있어요.');
      return;
    }
    let s: MediaStream;
    try {
      s = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name;
      onError(name === 'NotAllowedError'
        ? '마이크 권한이 꺼져 있어요. 주소창의 자물쇠 아이콘에서 마이크를 허용해 주세요.'
        : name === 'NotFoundError' ? '마이크를 찾을 수 없어요.' : '마이크를 켤 수 없어요.');
      return;
    }
    const mime = pickMime();
    const rec = new MediaRecorder(s, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (ev) => { if (ev.data.size > 0) chunks.push(ev.data); };
    rec.onstop = async () => {
      const type = rec.mimeType || mime || 'audio/webm';
      cleanup();
      if (cancelled.current) { setState('idle'); return; }
      setState('processing');
      try {
        const r = await postStt(new Blob(chunks, { type }), `voice.${extOf(type)}`);
        if (r.route === 'unsupported') onError('아직 지원하지 않는 언어예요. 한국어·영어·중국어로 말씀해 주세요.');
        else onResult(r.text, r.language);
      } catch (e) {
        onError(e instanceof ChatApiError ? e.message : '음성을 인식하지 못했어요. 다시 말씀해 주세요.');
      } finally {
        setState('idle');
      }
    };
    recorder.current = rec;
    stream.current = s;
    cancelled.current = false;
    rec.start();
    setSeconds(0);
    setState('recording');
    const began = Date.now();
    timer.current = window.setInterval(() => {
      const sec = Math.floor((Date.now() - began) / 1000);
      setSeconds(sec);
      if (sec >= maxSeconds) stop();
    }, 250);
  }, [cleanup, maxSeconds, onError, onResult, stop]);

  const toggle = useCallback(() => {
    if (state === 'recording') stop();
    else if (state === 'idle') void start();
  }, [start, state, stop]);

  // 화면을 떠나면 녹음 취소 + 마이크 끄기
  useEffect(() => () => {
    cancelled.current = true;
    if (recorder.current?.state === 'recording') recorder.current.stop();
    cleanup();
  }, [cleanup]);

  return { state, seconds, toggle };
}
