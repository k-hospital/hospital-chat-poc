import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Icon } from '../../shared/ui/icons';
import { ChatApiError } from '../../shared/api/chat';
import {
  hhmm, postCallback, startHandoff, wsUrl,
  type HandoffMessage, type HandoffReason, type TranscriptLine,
} from '../../shared/api/handoff';
import styles from './HandoffView.module.css';

type Phase = 'starting' | 'waiting' | 'connected' | 'closed' | 'lost' | 'callback' | 'callback_done' | 'error';

const REASON_TEXT: Record<Exclude<HandoffReason, null>, string> = {
  closed_hours: '지금은 상담 시간이 아니에요.',
  no_agent: '지금 연결할 수 있는 상담원이 없어요.',
};
const TIMES = ['오전 (09–12시)', '오후 (13–17시)', '언제든'];

// 상담 안내 — 실제 동작과 같아야 한다 (대화는 저장하지 않음: backend/handoff.py)
const NOTICE: ReactNode[] = [
  '원활한 상담을 위해 챗봇과 나눈 대화가 상담원에게 전달됩니다.',
  <><strong>상담 내용은 저장되지 않으며</strong>, 상담이 끝나면 삭제됩니다.</>,
  '주민등록번호, 카드번호 등 민감한 개인정보는 입력하지 마세요.',
  '예약 변경 등 본인 확인이 필요한 업무는 상담원이 별도로 안내해 드립니다.',
  '진단·처방은 진료를 통해 확인해 주세요. 응급 상황이면 119에 연락하세요.',
];

function Notice() {
  return (
    <section className={styles.notice} aria-label="상담 안내">
      <p className={styles.noticeTitle}><Icon name="info" size={14} strokeWidth={2.2} /> 상담 전 확인해 주세요</p>
      <ul>{NOTICE.map((n, i) => <li key={i}>{n}</li>)}</ul>
    </section>
  );
}

// 상담원 연결 (국내 전용). mode="callback"이면 바로 콜백 요청 화면 (야간·휴일 버튼)
export function HandoffView({ mode, transcript, hoursText, onBack }: {
  mode: 'agent' | 'callback';
  transcript: TranscriptLine[];
  hoursText: string;
  onBack: () => void;
}) {
  const [phase, setPhase] = useState<Phase>(mode === 'callback' ? 'callback' : 'starting');
  const [reason, setReason] = useState<string | null>(null);
  const [hours, setHours] = useState(hoursText);
  const [ticket, setTicket] = useState<string | null>(null);
  const [position, setPosition] = useState(0);
  const [messages, setMessages] = useState<HandoffMessage[]>([]);
  const [closedBy, setClosedBy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [reconnect, setReconnect] = useState(0);
  const ws = useRef<WebSocket | null>(null);
  const started = useRef(false);
  const end = useRef<HTMLDivElement>(null);

  // 1) 대기표 받기 — 개발 모드(StrictMode)에서 두 번 실행되지 않게 ref로 막는다
  useEffect(() => {
    if (mode !== 'agent' || started.current) return;
    started.current = true;
    startHandoff(transcript)
      .then((r) => {
        setHours(r.hours_text || hoursText);
        if (r.available && r.ticket) {
          setTicket(r.ticket);
          setPosition(r.position ?? 1);
          setPhase('waiting');
        } else {
          setReason(r.reason ? REASON_TEXT[r.reason] : null);
          setPhase('callback');
        }
      })
      .catch((e) => { setError(e instanceof ChatApiError ? e.message : '연결하지 못했어요.'); setPhase('error'); });
  }, [mode, transcript, hoursText]);

  // 2) 실시간 연결 (끊기면 '다시 연결' — 서버가 60초 동안 자리를 유지)
  useEffect(() => {
    if (!ticket) return;
    const sock = new WebSocket(wsUrl(`/v1/handoff/ws/${ticket}`));
    ws.current = sock;
    let finished = false;
    sock.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'queue') { setPosition(m.position); setPhase('waiting'); }
      else if (m.type === 'requeued') setPhase('waiting');
      else if (m.type === 'connected') { setMessages(m.messages ?? []); setPhase('connected'); }
      else if (m.type === 'message') setMessages((ms) => [...ms, { from: m.from, text: m.text, ts: m.ts }]);
      else if (m.type === 'closed') { finished = true; setClosedBy(m.by); setPhase('closed'); }
    };
    sock.onclose = () => {
      if (ws.current === sock && !finished) setPhase((p) => (p === 'waiting' || p === 'connected' ? 'lost' : p));
    };
    return () => { finished = true; sock.close(); if (ws.current === sock) ws.current = null; };
  }, [ticket, reconnect]);

  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [messages, phase]);

  const send = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: 'message', text: t }));
    setMessages((ms) => [...ms, { from: 'user', text: t, ts: Date.now() / 1000 }]);
    setText('');
  };

  const leave = () => {
    if (ws.current?.readyState === WebSocket.OPEN && (phase === 'waiting' || phase === 'connected')) {
      ws.current.send(JSON.stringify({ type: 'close' }));
    }
    onBack();
  };

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <button type="button" className={styles.iconBtn} onClick={leave} aria-label="나가기">
          <Icon name="back" size={20} strokeWidth={2.2} />
        </button>
        <h1>{phase === 'callback' || phase === 'callback_done' ? '상담원 콜백 요청' : '상담원 연결'}</h1>
        {(phase === 'waiting' || phase === 'connected') && (
          <button type="button" className={styles.endBtn} onClick={leave}>상담 종료</button>
        )}
      </header>

      <div className={styles.body} aria-live="polite">
        {phase === 'starting' && <p className={styles.card}>상담원 연결을 준비하고 있어요…</p>}

        {(phase === 'waiting' || phase === 'connected') && <Notice />}

        {phase === 'waiting' && (
          <div className={styles.card}>
            <p className={styles.big}>대기 순번 <strong>{position}</strong>번</p>
            <p className={styles.sub}>상담원이 연결되면 바로 대화를 시작할 수 있어요. 이 화면을 닫지 말고 기다려 주세요.</p>
          </div>
        )}

        {(phase === 'connected' || phase === 'closed' || phase === 'lost') && messages.map((m, i) => (
          m.from === 'system'
            ? <p key={i} className={styles.system}>{m.text}</p>
            : <p key={i} className={m.from === 'user' ? styles.mine : styles.theirs}>
                {m.text}<time>{hhmm(m.ts)}</time>
              </p>
        ))}

        {phase === 'closed' && (
          <div className={styles.card}>
            <p className={styles.big}>상담이 종료되었어요</p>
            <p className={styles.sub}>{closedBy === 'agent' ? '상담원이 상담을 마쳤습니다.' : '이용해 주셔서 감사합니다.'} 대화 내용은 저장되지 않습니다.</p>
            <button type="button" className={styles.primary} onClick={onBack}>처음으로</button>
          </div>
        )}

        {phase === 'lost' && (
          <div className={styles.card}>
            <p className={styles.big}>연결이 끊겼어요</p>
            <p className={styles.sub}>1분 안에 다시 연결하면 이어서 상담할 수 있어요.</p>
            <button type="button" className={styles.primary} onClick={() => setReconnect((n) => n + 1)}>다시 연결</button>
          </div>
        )}

        {phase === 'error' && (
          <div className={styles.card}>
            <p className={styles.big}>{error}</p>
            <button type="button" className={styles.primary} onClick={() => setPhase('callback')}>콜백 요청하기</button>
          </div>
        )}

        {phase === 'callback' && <CallbackForm reason={reason} hours={hours} onDone={() => setPhase('callback_done')} />}

        {phase === 'callback_done' && (
          <div className={styles.card}>
            <p className={styles.big}>콜백 요청이 접수되었어요</p>
            <p className={styles.sub}>상담 시간({hours})에 상담원이 남겨 주신 번호로 연락드립니다.</p>
            <button type="button" className={styles.primary} onClick={onBack}>처음으로</button>
          </div>
        )}

        {(phase === 'callback' || phase === 'callback_done') && (
          <p className={styles.emergency}>
            <Icon name="alert" size={15} strokeWidth={2.2} /> 응급 상황이면 기다리지 말고 119에 전화하거나 가까운 응급실로 가세요.
            <a href="tel:119">119 전화</a>
          </p>
        )}
        <div ref={end} />
      </div>

      {phase === 'connected' && (
        <form className={styles.inputRow} onSubmit={send}>
          <label htmlFor="handoff-input" className={styles.srOnly}>상담원에게 보낼 메시지</label>
          <input id="handoff-input" value={text} maxLength={500} autoComplete="off"
            placeholder="상담원에게 메시지를 보내세요" onChange={(e) => setText(e.target.value)} />
          <button type="submit" className={styles.sendBtn} aria-label="보내기" disabled={!text.trim()}>
            <Icon name="send" size={18} strokeWidth={2.4} />
          </button>
        </form>
      )}
    </div>
  );
}

function CallbackForm({ reason, hours, onDone }: { reason: string | null; hours: string; onDone: () => void }) {
  const [phone, setPhone] = useState('');
  const [time, setTime] = useState(TIMES[2]);
  const [note, setNote] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await postCallback(phone, time, note);
      onDone();
    } catch (err) {
      setError(err instanceof ChatApiError ? err.message : '접수하지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className={styles.card} onSubmit={submit}>
      {reason && <p className={styles.big}>{reason}</p>}
      <p className={styles.sub}>전화번호를 남겨 주시면 상담 시간({hours})에 상담원이 연락드려요.</p>
      <label className={styles.field}>
        <span>휴대전화 번호</span>
        <input type="tel" inputMode="tel" value={phone} placeholder="010-1234-5678" required
          onChange={(e) => setPhone(e.target.value)} />
      </label>
      <fieldset className={styles.field}>
        <legend>연락받기 편한 시간</legend>
        <div className={styles.chips}>
          {TIMES.map((t) => (
            <label key={t} className={`${styles.chip} ${time === t ? styles.chipOn : ''}`}>
              <input type="radio" name="cb-time" value={t} checked={time === t} onChange={() => setTime(t)} />{t}
            </label>
          ))}
        </div>
      </fieldset>
      <label className={styles.field}>
        <span>문의 내용 (선택)</span>
        <textarea value={note} maxLength={200} rows={3} placeholder="예: 정형외과 진료 예약 문의"
          onChange={(e) => setNote(e.target.value)} />
      </label>
      <label className={styles.consent}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>상담원 회신을 위해 전화번호를 수집하는 데 동의합니다. 회신 후 또는 7일이 지나면 삭제됩니다.</span>
      </label>
      {error && <p className={styles.error} role="alert">{error}</p>}
      <button type="submit" className={styles.primary} disabled={!consent || !phone.trim() || busy}>
        {busy ? '접수 중…' : '콜백 요청하기'}
      </button>
    </form>
  );
}
