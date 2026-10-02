import { useEffect, useState } from 'react';
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';
import type { ChatConfig } from './features/home/types';

// 백엔드 주소: 배포 시 VITE_API_BASE 환경변수로 지정 (비우면 같은 도메인의 /v1)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export default function App() {
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const forceNight = params.get('night') === '1'; // 데모용: ?night=1 이면 야간 화면

    fetch(`${API_BASE}/v1/config`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((c: ChatConfig) => setConfig(forceNight ? { ...c, isOperatingHours: false } : c))
      // 백엔드가 없으면 목업으로 화면 표시 (프론트만 배포해도 데모 가능)
      .catch(() => setConfig({ ...mockConfig, isOperatingHours: !forceNight }));
  }, []);

  const show = (msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 2000);
  };

  if (!config) return null;

  return (
    <>
      <MainScreen
        config={config}
        handlers={{
          // TODO: 대화 화면 전환 + POST /v1/chat/messages
          onAction: (m) => show(`${m.label} → intent: ${m.intent}${m.requiresAuth ? ' (인증 필요)' : ''}`),
          onSendText: (t) => show(`질문 전송: ${t}`),
          onAgent: () => show('상담원 연결 (준비 중)'),
          onCallback: () => show('콜백 요청 (준비 중)'),
        }}
      />
      {notice && (
        <div role="status" style={{
          position: 'fixed', left: '50%', bottom: 120, transform: 'translateX(-50%)',
          background: '#152238', color: '#fff', padding: '10px 16px', borderRadius: 10,
          fontSize: 13, fontFamily: 'inherit', maxWidth: '90vw',
        }}>{notice}</div>
      )}
    </>
  );
}
