import { useEffect, useRef, useState } from 'react';
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';
import type { ChatConfig } from './shared/types/config';
import { PageViewer, type PageQuery } from './features/page/PageViewer';
import { SettingsScreen } from './features/settings/SettingsScreen';
import { AGENT_KEY, CALLBACK_KEY, loadLinks, saveLinks, type LinkMap } from './shared/links/linkStore';
import { routeQuestion, routeSuggestion, type RouteResult } from './shared/chat/intentRouter';
import { classifyWithServer, type RoutedIntent } from './shared/chat/llmRouter';
import { HOME_SCREEN, screenSuggestions, type Suggestion } from './shared/chat/suggestions';
import { ChatInputBar, type ChatEcho } from './shared/ui/ChatInputBar';
import styles from './App.module.css';

// 백엔드 주소: 배포 시 VITE_API_BASE 환경변수로 지정 (비우면 같은 도메인의 /v1)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export default function App() {
  const [config, setConfig] = useState<ChatConfig | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<'home' | 'settings'>('home');
  // screen: 지금 화면의 기능(intent) — 화면별 추천 질문 목록을 고르는 데 사용
  const [page, setPage] = useState<{ url: string; title: string; screen: string; query?: PageQuery } | null>(null);
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
    setPage({ url, title: label, screen: key });
  };

  // 한 기능으로 이동한다. 질문에 요청이 여러 개였다면 남은 기능은 입력 바 위 칩으로 이어서 열 수 있다
  // (연결 페이지는 챗봇 안 화면 하나라서 한 번에 하나만 연다)
  const goTo = (item: RoutedIntent, rest: RoutedIntent[], question: string) => {
    const chips = rest.map((r, i) => ({
      label: r.label,
      onClick: () => goTo(r, rest.filter((_, j) => j !== i), question),
    }));
    const url = links[item.intent];
    if (!url) {
      setEcho({ question, tone: 'normal', reply: `'${item.label}' 서비스는 준비중입니다.`, chips });
      return;
    }
    setView('home');
    setPage({ url, title: item.label, screen: item.intent, query: { text: question, topic: item.topic } });
    // 이동한 화면 상단에 입력 내용이 표시되므로 말풍선은 닫는다 (이어서 볼 기능이 있을 때만 칩 안내)
    setEcho(rest.length > 0 ? { question, tone: 'normal', reply: '이어서 궁금하신 내용도 볼 수 있어요.', chips } : null);
  };

  // 판별 결과 표시: 응급 안내 / 해당 화면 이동 / 추천 메뉴. rest 는 이어서 열 수 있는 나머지 기능
  const showResult = (question: string, r: RouteResult, rest: RoutedIntent[] = []) => {
    if (!config) return;
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
    goTo({ intent: r.intent, label: r.label, topic: r.topic }, rest, question);
  };

  // 질문 입력
  // - 추천 질문을 골랐다면(suggestion) 엑셀에서 정한 기능으로 이동한다 (응급 검사만 먼저)
  // - 직접 입력은 응급 규칙을 먼저 보고, 서버(LLM)가 있으면 서버로 분류한다.
  //   서버가 없거나 실패하면 키워드 규칙 결과를 쓴다
  const latestAsk = useRef(0);
  const ask = (question: string, suggestion?: Suggestion) => {
    if (!config) return;
    latestAsk.current += 1;
    const id = latestAsk.current;
    if (suggestion) return showResult(question, routeSuggestion(question, suggestion.intent, suggestion.label));

    const byRules = routeQuestion(question);
    if (byRules.kind === 'emergency' || !config.llmRouting) return showResult(question, byRules);

    setEcho({ question, tone: 'normal', reply: '질문을 확인하고 있어요…' });
    void classifyWithServer(question, API_BASE).then((items) => {
      if (id !== latestAsk.current) return; // 기다리는 동안 다른 질문을 보냈다면 이전 결과는 버린다
      if (!items) return showResult(question, byRules);
      const [first, ...rest] = items;
      if (first.intent === 'emergency') return showResult(question, { kind: 'emergency' });
      if (first.intent === 'unknown') return showResult(question, { kind: 'unknown' });
      const more = rest.filter((r) => r.intent !== 'emergency' && r.intent !== 'unknown');
      goTo(first, more, question);
    });
  };

  const save = (next: LinkMap) => {
    const ok = saveLinks(next);
    if (ok) setLinks(next);
    return ok;
  };

  if (!config) return null;

  const inSettings = !page && view === 'settings';
  const suggestions = screenSuggestions(page?.screen ?? HOME_SCREEN);

  return (
    <div className={styles.shell}>
      <div className={styles.content}>
        {page ? (
          // 같은 화면에 다른 질문이 오면 새로 불러오지 않고 입력 문구만 다시 전달 (예: 오시는 길 탭 전환)
          <PageViewer key={page.url} url={page.url} title={page.title}
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
        <ChatInputBar disclaimer={config.disclaimer} echo={echo} suggestions={suggestions} onSend={ask} onCloseEcho={() => setEcho(null)} />
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
