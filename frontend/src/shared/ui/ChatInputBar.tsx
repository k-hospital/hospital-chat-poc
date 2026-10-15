import { useState, type FormEvent, type KeyboardEvent } from 'react';
import { Icon } from './icons';
import { matchesQuery, type Suggestion } from '../chat/suggestions';
import { useVoiceInput, voiceSupported } from '../speech/useVoiceInput';
import styles from './ChatInputBar.module.css';

// 질문 직후 입력창 위에 보여 주는 한 번의 주고받기 (내 질문 + 안내)
export interface ChatEcho {
  question: string;
  reply: string;
  tone: 'normal' | 'danger';
  chips?: { label: string; onClick: () => void }[];
  call119?: boolean;
}

const DEFAULT_DISCLAIMER = 'AI 안내는 참고용이며 진단이 아닙니다';
const LIST_ID = 'chat-suggest';

// 모든 화면 아래에 고정되는 공통 질문 입력 바 — 화면이 바뀌어도 입력 중인 글자 유지
// 입력창을 누르면 지금 화면에 맞는 추천 질문 목록을 보여 주고, 고르면 바로 전송한다
export function ChatInputBar({ disclaimer, echo, suggestions, onSend, onVoice, onCloseEcho }: {
  disclaimer?: string;
  echo: ChatEcho | null;
  suggestions: Suggestion[];
  // 추천 질문을 골랐다면 suggestion(연결 기능 포함)을 함께 넘긴다
  onSend: (text: string, suggestion?: Suggestion) => void;
  onVoice?: (text: string, lang: string | null) => void;   // 음성 인식 결과 (바로 전송, ai-backend /v1/stt)
  onCloseEcho: () => void;
}) {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // 면책 문구는 관리자가 비워도 기본 문구로 강제 노출
  const notice = disclaimer?.trim() || DEFAULT_DISCLAIMER;

  const [voiceError, setVoiceError] = useState<string | null>(null);
  const voice = useVoiceInput({
    onResult: (t, lang) => { setVoiceError(null); onVoice?.(t, lang); },
    onError: setVoiceError,
  });
  const canVoice = Boolean(onVoice) && voiceSupported();
  const mmss = `${Math.floor(voice.seconds / 60)}:${String(voice.seconds % 60).padStart(2, '0')}`;

  const items = suggestions.filter((s) => matchesQuery(s.text, text));
  const showList = open && items.length > 0;

  const close = () => { setOpen(false); setActive(-1); };

  const send = (t: string, suggestion?: Suggestion) => {
    onSend(t, suggestion);
    setText('');
    close();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    // 추천 질문과 똑같이 직접 입력해도 같은 기능으로 이동 (띄어쓰기 차이는 무시)
    const squash = (s: string) => s.replace(/\s+/g, '');
    if (t) send(t, suggestions.find((s) => squash(s.text) === squash(t)));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') return close();
    if (!showList) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const step = e.key === 'ArrowDown' ? 1 : -1;
      setActive((i) => (i + step + items.length) % items.length);
    } else if (e.key === 'Enter' && active >= 0 && active < items.length) {
      e.preventDefault();
      send(items[active].text, items[active]);
    }
  };

  return (
    <footer className={styles.bar}>
      {showList ? (
        <section className={styles.suggest} aria-label="추천 질문">
          <p className={styles.suggestTitle}>이렇게 물어보세요</p>
          <ul id={LIST_ID} role="listbox" className={styles.suggestList}>
            {items.map((s, i) => (
              <li key={s.text} id={`${LIST_ID}-${i}`} role="option" aria-selected={i === active}
                className={`${styles.suggestItem} ${i === active ? styles.suggestActive : ''}`}
                // 목록을 누르는 동안 입력창이 포커스를 잃어 목록이 닫히지 않도록
                onMouseDown={(e) => { e.preventDefault(); send(s.text, s); }}
                onMouseEnter={() => setActive(i)}>
                <span className={styles.suggestIcon}><Icon name={s.icon} size={16} /></span>
                {s.text}
              </li>
            ))}
          </ul>
        </section>
      ) : echo && (
        <section className={`${styles.echo} ${echo.tone === 'danger' ? styles.danger : ''}`} aria-live="polite">
          <button type="button" className={styles.close} onClick={onCloseEcho} aria-label="안내 닫기">✕</button>
          <p className={styles.question}>{echo.question}</p>
          <p className={styles.reply}>
            {echo.tone === 'danger' && <Icon name="alert" size={16} strokeWidth={2.2} className={styles.replyIcon} />}
            {echo.reply}
          </p>
          {echo.call119 && <a className={styles.call} href="tel:119">119 전화</a>}
          {echo.chips && echo.chips.length > 0 && (
            <div className={styles.chips}>
              {echo.chips.map((c) => (
                <button key={c.label} type="button" className={styles.chip} onClick={c.onClick}>{c.label}</button>
              ))}
            </div>
          )}
        </section>
      )}
      {voice.state === 'recording' ? (
        <p className={styles.voiceStatus} role="status"><span className={styles.dot} /> 듣고 있어요 {mmss} · 다 말씀하셨으면 마이크를 다시 눌러 주세요</p>
      ) : voice.state === 'processing' ? (
        <p className={styles.voiceStatus} role="status">말씀하신 내용을 확인하고 있어요…</p>
      ) : voiceError ? (
        <p className={`${styles.voiceStatus} ${styles.voiceError}`} role="alert">{voiceError}</p>
      ) : (
        <p className={styles.disclaimer}><Icon name="info" size={13} strokeWidth={2} /> {notice}</p>
      )}
      <form className={styles.inputRow} onSubmit={submit}>
        <label htmlFor="chat-ask" className={styles.srOnly}>질문 입력</label>
        <input id="chat-ask" value={text} placeholder="증상이나 궁금한 점을 물어보세요" autoComplete="off"
          role="combobox" aria-expanded={showList} aria-controls={LIST_ID} aria-autocomplete="list"
          aria-activedescendant={showList && active >= 0 ? `${LIST_ID}-${active}` : undefined}
          onChange={(e) => { setText(e.target.value); setOpen(true); setActive(-1); }}
          onFocus={() => setOpen(true)} onBlur={close} onKeyDown={onKeyDown} />
        {canVoice && (
          <button type="button" className={`${styles.micBtn} ${voice.state === 'recording' ? styles.micOn : ''}`}
            aria-label={voice.state === 'recording' ? '녹음 끝내기' : '음성 입력'} aria-pressed={voice.state === 'recording'}
            disabled={voice.state === 'processing'} onClick={() => { setVoiceError(null); voice.toggle(); }}>
            <Icon name="mic" />
          </button>
        )}
        <button type="submit" className={styles.sendBtn} aria-label="보내기" disabled={!text.trim()}>
          <Icon name="send" size={18} strokeWidth={2.4} />
        </button>
      </form>
    </footer>
  );
}
