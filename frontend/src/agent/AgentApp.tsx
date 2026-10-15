import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { ChatApiError } from '../shared/api/chat';
import {
  agentLogin, doneCallback, hhmm, listCallbacks, wsUrl,
  type Callback, type HandoffMessage, type TranscriptLine,
} from '../shared/api/handoff';
import styles from './AgentApp.module.css';

// 상담원 화면 (/agent) — 국내 전용. 대기 목록 · 동시 상담(최대 10) · 콜백 목록
interface Waiting { ticket: string; created: number; preview: string }
interface Chat {
  ticket: string; created: number; transcript: TranscriptLine[]; messages: HandoffMessage[];
  user_online: boolean; unread: number; closed?: string;
}

const TOKEN_KEY = 'agent.token';
const NAME_KEY = 'agent.name';
const load = (k: string) => { try { return sessionStorage.getItem(k); } catch { return null; } };
const store = (k: string, v: string | null) => {
  try { if (v === null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch { /* 저장 불가 브라우저 */ }
};

export default function AgentApp() {
  const [token, setToken] = useState<string | null>(() => load(TOKEN_KEY));
  const [name, setName] = useState(() => load(NAME_KEY) ?? '');
  // 자식 effect의 의존성이라 매번 새로 만들지 않는다 (WebSocket 재연결 반복 방지)
  const logout = useCallback(() => { store(TOKEN_KEY, null); setToken(null); }, []);
  if (!token) {
    return <Login onLogin={(t, n) => { store(TOKEN_KEY, t); store(NAME_KEY, n); setToken(t); setName(n); }} />;
  }
  return <Console token={token} name={name} onLogout={logout} />;
}

function Login({ onLogin }: { onLogin: (token: string, name: string) => void }) {
  const [name, setName] = useState(load(NAME_KEY) ?? '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const r = await agentLogin(password, name.trim() || '상담원');
      onLogin(r.token, r.name);
    } catch (err) {
      setError(err instanceof ChatApiError ? err.message : '로그인하지 못했습니다.');
    }
  };
  return (
    <div className={styles.loginWrap}>
      <form className={styles.login} onSubmit={submit}>
        <h1>상담원 로그인</h1>
        <label>이름<input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 김상담" maxLength={20} /></label>
        <label>비밀번호<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <p className={styles.error} role="alert">{error}</p>}
        <button type="submit" className={styles.primary}>로그인</button>
      </form>
    </div>
  );
}

function Console({ token, name, onLogout }: { token: string; name: string; onLogout: () => void }) {
  const [online, setOnline] = useState(false);
  const [maxChats, setMaxChats] = useState(10);
  const [waiting, setWaiting] = useState<Waiting[]>([]);
  const [chats, setChats] = useState<Chat[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<'chats' | 'callbacks'>('chats');
  const [notice, setNotice] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const ws = useRef<WebSocket | null>(null);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;

  const updateChat = (ticket: string, fn: (c: Chat) => Chat) =>
    setChats((cs) => cs.map((c) => (c.ticket === ticket ? fn(c) : c)));

  useEffect(() => {
    const sock = new WebSocket(wsUrl(`/v1/agent/ws?token=${encodeURIComponent(token)}`));
    ws.current = sock;
    let timer: number | undefined;
    sock.onopen = () => setOnline(true);
    sock.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'init') {
        setMaxChats(m.max_chats);
        setWaiting(m.waiting);
        setChats(m.chats.map((c: Chat) => ({ ...c, unread: 0 })));
      } else if (m.type === 'waiting') {
        setWaiting(m.items);
      } else if (m.type === 'assigned') {
        setChats((cs) => [...cs.filter((c) => c.ticket !== m.chat.ticket), { ...m.chat, unread: 0 }]);
        setSelected(m.chat.ticket);
        setTab('chats');
      } else if (m.type === 'message') {
        updateChat(m.ticket, (c) => ({
          ...c, messages: [...c.messages, { from: m.from, text: m.text, ts: m.ts }],
          unread: selectedRef.current === m.ticket ? 0 : c.unread + 1,
        }));
      } else if (m.type === 'user_left') {
        updateChat(m.ticket, (c) => ({ ...c, user_online: false }));
      } else if (m.type === 'user_back') {
        updateChat(m.ticket, (c) => ({ ...c, user_online: true }));
      } else if (m.type === 'closed') {
        updateChat(m.ticket, (c) => ({ ...c, closed: m.by }));
      } else if (m.type === 'error') {
        setNotice(m.message);
        window.setTimeout(() => setNotice(null), 3000);
      }
    };
    sock.onclose = (ev) => {
      setOnline(false);
      if (ev.code === 4401) { onLogout(); return; }        // 로그인 만료
      if (ws.current === sock) timer = window.setTimeout(() => setRetry((n) => n + 1), 3000);   // 자동 재연결
    };
    return () => { window.clearTimeout(timer); if (ws.current === sock) ws.current = null; sock.close(); };
  }, [token, retry, onLogout]);

  const sendWs = (payload: object) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(payload));
  };
  const active = chats.filter((c) => !c.closed);
  const current = chats.find((c) => c.ticket === selected) ?? null;

  const select = (ticket: string) => {
    setSelected(ticket);
    updateChat(ticket, (c) => ({ ...c, unread: 0 }));
  };
  const removeClosed = (ticket: string) => {
    setChats((cs) => cs.filter((c) => c.ticket !== ticket));
    if (selected === ticket) setSelected(null);
  };

  return (
    <div className={styles.app}>
      <header className={styles.top}>
        <h1>상담원 화면</h1>
        <span className={online ? styles.on : styles.off}>{online ? '연결됨' : '연결 중…'}</span>
        <span className={styles.me}>{name}</span>
        <button type="button" className={styles.ghost} onClick={onLogout}>로그아웃</button>
      </header>
      {notice && <p className={styles.notice} role="status">{notice}</p>}
      <div className={styles.main}>
        <aside className={styles.side}>
          <nav className={styles.tabs} role="tablist">
            <button type="button" role="tab" aria-selected={tab === 'chats'} onClick={() => setTab('chats')}>상담</button>
            <button type="button" role="tab" aria-selected={tab === 'callbacks'} onClick={() => setTab('callbacks')}>콜백</button>
          </nav>
          {tab === 'chats' && (
            <>
              <h2>대기 {waiting.length}</h2>
              {waiting.length === 0 && <p className={styles.empty}>대기 중인 이용자가 없습니다.</p>}
              <ul className={styles.list}>
                {waiting.map((w) => (
                  <li key={w.ticket} className={styles.item}>
                    <div><strong>{w.preview || '(챗봇 대화 없음)'}</strong><small>{hhmm(w.created)} 접수</small></div>
                    <button type="button" className={styles.small} disabled={active.length >= maxChats}
                      onClick={() => sendWs({ type: 'accept', ticket: w.ticket })}>연결</button>
                  </li>
                ))}
              </ul>
              <h2>상담 중 {active.length}/{maxChats}</h2>
              <ul className={styles.list}>
                {chats.map((c) => (
                  <li key={c.ticket}>
                    <button type="button" className={`${styles.chatItem} ${selected === c.ticket ? styles.sel : ''}`}
                      onClick={() => select(c.ticket)}>
                      <span>{c.transcript.find((t) => t.role === 'user')?.text.slice(0, 24) || '이용자'}</span>
                      {c.closed ? <em>종료</em> : !c.user_online ? <em>연결 끊김</em> : null}
                      {c.unread > 0 && <b>{c.unread}</b>}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
          {tab === 'callbacks' && <p className={styles.empty}>오른쪽에서 콜백 요청을 확인하세요.</p>}
        </aside>
        <section className={styles.panel}>
          {tab === 'callbacks' ? <Callbacks token={token} onUnauthorized={onLogout} />
            : current ? (
              <ChatPanel chat={current}
                onSend={(text) => {
                  sendWs({ type: 'message', ticket: current.ticket, text });
                  updateChat(current.ticket, (c) => ({ ...c, messages: [...c.messages, { from: 'agent', text, ts: Date.now() / 1000 }] }));
                }}
                onClose={() => sendWs({ type: 'close', ticket: current.ticket })}
                onRemove={() => removeClosed(current.ticket)} />
            ) : <p className={styles.empty}>왼쪽에서 상담을 선택하거나 대기 중인 이용자를 연결하세요.</p>}
        </section>
      </div>
    </div>
  );
}

function ChatPanel({ chat, onSend, onClose, onRemove }: {
  chat: Chat; onSend: (text: string) => void; onClose: () => void; onRemove: () => void;
}) {
  const [text, setText] = useState('');
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [chat.messages.length, chat.ticket]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (t) { onSend(t); setText(''); }
  };
  return (
    <div className={styles.chat}>
      <div className={styles.chatHead}>
        <strong>{hhmm(chat.created)} 접수 상담</strong>
        {!chat.user_online && !chat.closed && <span className={styles.off}>이용자 연결 끊김 (1분 안에 돌아오지 않으면 종료)</span>}
        {chat.closed
          ? <button type="button" className={styles.ghost} onClick={onRemove}>목록에서 지우기</button>
          : <button type="button" className={styles.danger} onClick={onClose}>상담 종료</button>}
      </div>
      <div className={styles.messages}>
        {chat.transcript.length > 0 && (
          <details className={styles.history} open>
            <summary>챗봇 대화 이력 ({chat.transcript.length})</summary>
            {chat.transcript.map((t, i) => (
              <p key={i}><b>{t.role === 'user' ? '이용자' : '챗봇'}</b> {t.text}</p>
            ))}
          </details>
        )}
        {chat.messages.map((m, i) => (
          m.from === 'system'
            ? <p key={i} className={styles.system}>{m.text}</p>
            : <p key={i} className={m.from === 'agent' ? styles.mine : styles.theirs}>{m.text}<time>{hhmm(m.ts)}</time></p>
        ))}
        {chat.closed && <p className={styles.system}>{chat.closed === 'agent' ? '상담을 종료했습니다.' : '이용자가 상담을 종료했습니다.'} 대화 내용은 저장되지 않습니다.</p>}
        <div ref={end} />
      </div>
      {!chat.closed && (
        <form className={styles.input} onSubmit={submit}>
          <input value={text} onChange={(e) => setText(e.target.value)} maxLength={1000} placeholder="메시지 입력 후 Enter" aria-label="메시지" />
          <button type="submit" className={styles.primary} disabled={!text.trim()}>보내기</button>
        </form>
      )}
    </div>
  );
}

function Callbacks({ token, onUnauthorized }: { token: string; onUnauthorized: () => void }) {
  const [items, setItems] = useState<Callback[]>([]);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    try {
      setItems((await listCallbacks(token)).items);
      setError(null);
    } catch (e) {
      if (e instanceof ChatApiError && e.code === 'UNAUTHORIZED') onUnauthorized();
      else setError('콜백 목록을 불러오지 못했습니다.');
    }
  }, [token, onUnauthorized]);
  useEffect(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(t);
  }, [refresh]);
  const done = async (id: number) => {
    try { await doneCallback(token, id); } finally { void refresh(); }
  };
  const when = (ts: number) => new Date(ts * 1000).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  return (
    <div className={styles.callbacks}>
      <div className={styles.chatHead}>
        <strong>콜백 요청 {items.length}건</strong>
        <span className={styles.hint}>처리 완료하면 바로 삭제되며, 7일이 지나면 자동 삭제됩니다.</span>
        <button type="button" className={styles.ghost} onClick={() => void refresh()}>새로고침</button>
      </div>
      {error && <p className={styles.error}>{error}</p>}
      {items.length === 0 ? <p className={styles.empty}>콜백 요청이 없습니다.</p> : (
        <table>
          <thead><tr><th>접수</th><th>전화번호</th><th>희망 시간</th><th>문의 내용</th><th /></tr></thead>
          <tbody>
            {items.map((c) => (
              <tr key={c.id}>
                <td>{when(c.created)}</td>
                <td><a href={`tel:${c.phone}`}>{c.phone}</a></td>
                <td>{c.preferred_time}</td>
                <td>{c.note || '-'}</td>
                <td><button type="button" className={styles.small} onClick={() => void done(c.id)}>처리 완료</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
