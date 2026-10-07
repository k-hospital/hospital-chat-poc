import { useEffect, useState } from 'react';
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';
import type { ChatConfig } from './features/home/types';
import { PageViewer } from './features/page/PageViewer';
import { SettingsScreen } from './features/settings/SettingsScreen';
import { AGENT_KEY, CALLBACK_KEY, loadLinks, saveLinks, type LinkMap } from './features/settings/linkStore';

// 백엔드 주소: 배포 시 VITE_API_BASE 환경변수로 지정 (비우면 같은 도메인의 /v1)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export default function App() {
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<'home' | 'settings'>('home');
  const [page, setPage] = useState<{ url: string; title: string } | null>(null);
  const [links, setLinks] = useState<LinkMap>(loadLinks);

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

  const isLinked = (key: string) => Boolean(links[key]);

  // 연결 주소가 등록돼 있으면 챗봇 안에서 이동, 없으면 "준비중" 안내 후 종료
  const openLink = (key: string, label: string) => {
    const url = links[key];
    if (!url) {
      show(`'${label}' 서비스는 준비중입니다`);
      return;
    }
    setPage({ url, title: label });
  };

  const save = (next: LinkMap) => {
    const ok = saveLinks(next);
    if (ok) setLinks(next);
    return ok;
  };

  if (!config) return null;

  return (
    <>
      {page ? (
        <PageViewer url={page.url} title={page.title} onBack={() => setPage(null)} />
      ) : view === 'settings' ? (
        <SettingsScreen config={config} links={links} onSave={save} onBack={() => setView('home')} />
      ) : (
        <MainScreen
          config={config}
          isLinked={isLinked}
          handlers={{
            onAction: (m) => openLink(m.intent, m.label),
            // TODO: 대화 화면 전환 + POST /v1/chat/messages
            onSendText: (t) => show(`질문 전송: ${t}`),
            onAgent: () => openLink(AGENT_KEY, '상담원 연결'),
            onCallback: () => openLink(CALLBACK_KEY, '콜백 요청'),
            onSettings: () => setView('settings'),
          }}
        />
      )}
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
