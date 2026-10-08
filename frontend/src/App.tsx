import { useEffect, useState } from 'react';
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';
import type { ChatConfig } from './shared/types/config';
import { PageViewer, type PageQuery } from './features/page/PageViewer';
import { SettingsScreen } from './features/settings/SettingsScreen';
import { AGENT_KEY, CALLBACK_KEY, loadLinks, saveLinks, type LinkMap } from './shared/links/linkStore';
import { routeQuestion } from './shared/chat/intentRouter';
import { ChatInputBar, type ChatEcho } from './shared/ui/ChatInputBar';
import styles from './App.module.css';

// 백엔드 주소: 배포 시 VITE_API_BASE 환경변수로 지정 (비우면 같은 도메인의 /v1)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export default function App() {
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<'home' | 'settings'>('home');
  const [page, setPage] = useState<{ url: string; title: string; query?: PageQuery } | null>(null);
  const [links, setLinks] = useState<LinkMap>(loadLinks);
  const [echo, setEcho] = useState<ChatEcho | null>(null);

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

  // 메뉴 선택: 연결 주소가 등록돼 있으면 챗봇 안에서 이동, 없으면 "준비중" 안내 후 종료
  const openLink = (key: string, label: string) => {
    const url = links[key];
    if (!url) {
      show(`'${label}' 서비스는 준비중입니다`);
      return;
    }
    setEcho(null);
    setPage({ url, title: label });
  };

  // 질문 입력: 판별 결과에 따라 응급 안내 / 해당 화면 이동 / 추천 메뉴
  const ask = (question: string) => {
    if (!config) return;
    const r = routeQuestion(question);
    if (r.kind === 'emergency') {
      setEcho({
        question, tone: 'danger', call119: true,
        reply: '응급 상황일 수 있어요. 지금 바로 119에 전화하거나 가까운 응급실로 가세요.',
      });
      return;
    }
    if (r.kind === 'unknown') {
      const menus = [{ intent: config.hero.intent, label: config.hero.title }, ...config.tiles]
        .filter((m) => isLinked(m.intent))
        .slice(0, 4);
      setEcho({
        question, tone: 'normal',
        reply: menus.length > 0 ? '정확히 이해하지 못했어요. 아래 메뉴에서 골라 보세요.' : '정확히 이해하지 못했어요. 다른 말로 다시 물어봐 주세요.',
        chips: menus.map((m) => ({ label: m.label, onClick: () => openLink(m.intent, m.label) })),
      });
      return;
    }
    const url = links[r.intent];
    if (!url) {
      setEcho({ question, tone: 'normal', reply: `'${r.label}' 서비스는 준비중입니다.` });
      return;
    }
    setEcho({ question, tone: 'normal', reply: r.reply });
    setView('home');
    setPage({ url, title: r.label, query: { text: question, topic: r.topic } });
  };

  const save = (next: LinkMap) => {
    const ok = saveLinks(next);
    if (ok) setLinks(next);
    return ok;
  };

  if (!config) return null;

  const inSettings = !page && view === 'settings';

  return (
    <div className={styles.shell}>
      <div className={styles.content}>
        {page ? (
          // 같은 화면으로 다른 질문이 오면 새로 불러와 입력 문구를 다시 전달
          <PageViewer key={`${page.url}|${page.query?.text ?? ''}`} url={page.url} title={page.title}
            query={page.query} onBack={() => { setPage(null); setEcho(null); }} />
        ) : inSettings ? (
          <SettingsScreen config={config} links={links} onSave={save} onBack={() => setView('home')} />
        ) : (
          <MainScreen
            config={config}
            isLinked={isLinked}
            handlers={{
              onAction: (m) => openLink(m.intent, m.label),
              onAgent: () => openLink(AGENT_KEY, '상담원 연결'),
              onCallback: () => openLink(CALLBACK_KEY, '콜백 요청'),
              onSettings: () => { setEcho(null); setView('settings'); },
            }}
          />
        )}
      </div>
      {/* 설정 화면은 하단 저장 버튼과 겹치므로 입력 바를 숨긴다 */}
      {!inSettings && (
        <ChatInputBar disclaimer={config.disclaimer} echo={echo} onSend={ask} onCloseEcho={() => setEcho(null)} />
      )}
      {notice && (
        <div role="status" style={{
          position: 'fixed', left: '50%', bottom: 120, transform: 'translateX(-50%)',
          background: '#152238', color: '#fff', padding: '10px 16px', borderRadius: 10,
          fontSize: 13, fontFamily: 'inherit', maxWidth: '90vw', zIndex: 10,
        }}>{notice}</div>
      )}
    </div>
  );
}
