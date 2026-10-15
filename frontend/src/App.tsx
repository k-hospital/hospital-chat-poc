import { useEffect, useMemo, useRef, useState } from 'react';
import { MainScreen } from './features/home/MainScreen';
import { mockConfig } from './features/home/mockConfig';
import type { ChatConfig } from './shared/types/config';
import { PageViewer, type PageQuery } from './features/page/PageViewer';
import { SettingsScreen } from './features/settings/SettingsScreen';
import { AGENT_KEY, CALLBACK_KEY, loadLinks, saveLinks, type LinkMap } from './shared/links/linkStore';
import { hoursText, isWithinHours, loadHours, saveHours, type OperatingHours } from './shared/hours/hoursStore';
import { routeQuestion, routeSuggestion, type RouteResult } from './shared/chat/intentRouter';
import { classifyWithServer, type RoutedIntent } from './shared/chat/llmRouter';
import { HOME_SCREEN, screenSuggestions, type Suggestion } from './shared/chat/suggestions';
import { ChatInputBar, type ChatEcho } from './shared/ui/ChatInputBar';
// AI 상담(외국어 답변)·음성·상담원 연결 — ai-backend(/v1/chat, /v1/stt, /v1/handoff)와 짝
import { ChatView, type ChatTurn } from './features/chat/ChatView';
import { HandoffView } from './features/handoff/HandoffView';
import { ChatApiError, postChat } from './shared/api/chat';
import type { TranscriptLine } from './shared/api/handoff';

// 한글이 하나도 없고 글자(영문·한자 등)가 있으면 외국어 질문 → ai-backend가 그 언어로 답변
const isForeign = (text: string) => !/[가-힣ㄱ-ㅎ]/.test(text) && /\p{L}/u.test(text);
import styles from './App.module.css';

// 백엔드 주소: 배포 시 VITE_API_BASE 환경변수로 지정 (비우면 같은 도메인의 /v1)
const API_BASE = import.meta.env.VITE_API_BASE ?? '';

// 데모용: ?night=1 이면 설정과 관계없이 야간 화면
const FORCE_NIGHT = new URLSearchParams(location.search).get('night') === '1';

export default function App() {
  const [serverConfig, setConfig] = useState<ChatConfig | null>(null);
  // ⚙ 설정에서 정한 상담 운영시간. 없으면(null) 서버가 알려 주는 운영시간을 쓴다
  const [hours, setHours] = useState<OperatingHours | null>(loadHours);
  // 운영 시간 경계를 넘으면 화면이 바뀌도록 분 단위로 시각을 갱신한다
  const [minute, setMinute] = useState(() => Math.floor(Date.now() / 60000));
  useEffect(() => {
    const t = window.setInterval(() => setMinute(Math.floor(Date.now() / 60000)), 15000);
    return () => window.clearInterval(t);
  }, []);
  const config = useMemo<ChatConfig | null>(() => {
    if (!serverConfig || !hours || FORCE_NIGHT) return serverConfig;
    return {
      ...serverConfig,
      isOperatingHours: isWithinHours(hours, new Date(minute * 60000)),
      operatingHoursText: hoursText(hours),
    };
  }, [serverConfig, hours, minute]);
  const [notice, setNotice] = useState<string | null>(null);
  const [view, setView] = useState<'home' | 'settings' | 'chat' | 'handoff'>('home');
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [handoffMode, setHandoffMode] = useState<'agent' | 'callback'>('agent');
  // screen: 지금 화면의 기능(intent) — 화면별 추천 질문 목록을 고르는 데 사용
  const [page, setPage] = useState<{ url: string; title: string; screen: string; query?: PageQuery } | null>(null);
  const [links, setLinks] = useState<LinkMap>(loadLinks);
  const [echo, setEcho] = useState<ChatEcho | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/config`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((c: ChatConfig) => setConfig(FORCE_NIGHT ? { ...c, isOperatingHours: false } : c))
      // 백엔드가 없으면 목업으로 화면 표시 (프론트만 배포해도 데모 가능)
      .catch(() => setConfig({ ...mockConfig, isOperatingHours: !FORCE_NIGHT }));
  }, []);

  const show = (msg: string) => {
    setNotice(msg);
    window.setTimeout(() => setNotice(null), 2000);
  };

  // 상담원 연결·콜백은 이 앱(HandoffView)이 직접 처리하므로 연결 주소 없이도 사용 가능
  const isLinked = (key: string) => key === AGENT_KEY || key === CALLBACK_KEY || Boolean(links[key]);

  // 외국어 질문 → AI 답변 화면 (ai-backend POST /v1/chat)
  const chat = async (question: string, lang?: string) => {
    const id = Date.now();
    setEcho(null);
    setPage(null);
    setView('chat');
    setTurns((ts) => [...ts, { id, question, status: 'loading' }]);
    try {
      const res = await postChat(question, lang);
      setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, status: 'done', res } : t)));
    } catch (e) {
      const error = e instanceof ChatApiError ? e.message : '잠시 서비스를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.';
      setTurns((ts) => ts.map((t) => (t.id === id ? { ...t, status: 'error', error } : t)));
    }
  };

  // 상담원 연결 (국내 전용) — mode="callback"이면 바로 콜백 요청
  const openHandoff = (mode: 'agent' | 'callback') => {
    setEcho(null);
    setPage(null);
    setHandoffMode(mode);
    setView('handoff');
  };
  // 상담원에게 넘길 AI 대화 (최근 10번)
  const transcript = useMemo<TranscriptLine[]>(() => turns.slice(-10).flatMap((t) => {
    const lines: TranscriptLine[] = [{ role: 'user', text: t.question }];
    if (t.res) lines.push({ role: 'bot', text: t.res.answer });
    return lines;
  }), [turns]);
  // 마지막 답변이 외국어면 상담원 연결 버튼을 숨긴다 (국내 전용)
  const lastLang = [...turns].reverse().find((t) => t.res)?.res?.lang ?? 'ko';

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
    if (isForeign(question)) return void chat(question);   // 외국어 입력 → AI 답변 (한국어는 아래 팀 흐름 그대로)

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

  // null 이면 설정을 지우고 서버 기준 운영시간으로 되돌린다
  const saveOperatingHours = (next: OperatingHours | null) => {
    const ok = saveHours(next);
    if (ok) setHours(next);
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
        ) : view === 'handoff' ? (
          <HandoffView mode={handoffMode} transcript={transcript} hoursText={config.operatingHoursText}
            onBack={() => setView(turns.length > 0 ? 'chat' : 'home')} />
        ) : view === 'chat' ? (
          <ChatView turns={turns} onBack={() => setView('home')}
            onAgent={lastLang === 'ko' ? () => openHandoff(config.isOperatingHours ? 'agent' : 'callback') : undefined} />
        ) : inSettings ? (
          // 설정 화면에는 서버 기준 값을 넘긴다 ("서버 기준" 운영시간 문구가 설정값에 덮이지 않게)
          <SettingsScreen config={serverConfig ?? config} links={links} onSave={save}
            hours={hours} onSaveHours={saveOperatingHours} onBack={() => setView('home')} />
        ) : (
          <MainScreen
            config={config}
            isLinked={isLinked}
            handlers={{
              onAction: (m) => openLink(m.intent, m.label),
              onAgent: () => openHandoff('agent'),
              onCallback: () => openHandoff('callback'),
              onSettings: () => { setEcho(null); setView('settings'); },
            }}
          />
        )}
      </div>
      {/* 설정 화면은 하단 저장 버튼과 겹치므로 입력 바를 숨긴다 */}
      {!inSettings && view !== 'handoff' && (
        <ChatInputBar disclaimer={config.disclaimer} echo={echo} suggestions={suggestions} onSend={ask}
          // 음성: 한국어는 입력과 같은 팀 흐름(응급·질문 분류), 영어·중국어는 그 언어로 AI 답변
          onVoice={(t, lang) => (lang && lang !== 'ko' ? void chat(t, lang) : ask(t))}
          onCloseEcho={() => setEcho(null)} />
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
