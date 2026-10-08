import { useState, type FormEvent } from 'react';
import { Icon } from './icons';
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

// 모든 화면 아래에 고정되는 공통 질문 입력 바 — 화면이 바뀌어도 입력 중인 글자 유지
export function ChatInputBar({ disclaimer, echo, onSend, onCloseEcho }: {
  disclaimer?: string;
  echo: ChatEcho | null;
  onSend: (text: string) => void;
  onCloseEcho: () => void;
}) {
  const [text, setText] = useState('');
  // 면책 문구는 관리자가 비워도 기본 문구로 강제 노출
  const notice = disclaimer?.trim() || DEFAULT_DISCLAIMER;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    onSend(t);
    setText('');
  };

  return (
    <footer className={styles.bar}>
      {echo && (
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
      <p className={styles.disclaimer}><Icon name="info" size={13} strokeWidth={2} /> {notice}</p>
      <form className={styles.inputRow} onSubmit={submit}>
        <label htmlFor="chat-ask" className={styles.srOnly}>질문 입력</label>
        <input id="chat-ask" value={text} onChange={(e) => setText(e.target.value)}
          placeholder="증상이나 궁금한 점을 물어보세요" autoComplete="off" />
        <button type="button" className={styles.micBtn} aria-label="음성 입력"><Icon name="mic" /></button>
        <button type="submit" className={styles.sendBtn} aria-label="보내기" disabled={!text.trim()}>
          <Icon name="send" size={18} strokeWidth={2.4} />
        </button>
      </form>
    </footer>
  );
}
