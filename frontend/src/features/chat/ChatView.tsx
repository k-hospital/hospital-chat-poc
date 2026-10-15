import { useEffect, useRef } from 'react';
import { Icon } from '../../shared/ui/icons';
import type { ChatResponse } from '../../shared/api/chat';
import styles from './ChatView.module.css';

// 외국어 답변의 출처 칩: "Hospital website (원래 한국어 제목)" — 답변 안 괄호 병기와 같은 원칙
const SOURCE_LABEL: Record<string, string> = { en: 'Hospital website', zh: '医院网站' };
const sourceLabel = (lang: string, title: string) => (SOURCE_LABEL[lang] ? `${SOURCE_LABEL[lang]} (${title})` : title);

// 한 번의 질문과 답변
export interface ChatTurn {
  id: number;
  question: string;
  status: 'loading' | 'done' | 'error';
  res?: ChatResponse;
  error?: string;
}

// AI 상담 대화 화면 — 질문은 하단 공통 입력 바(ChatInputBar)에서 받고, 여기서는 대화 목록만 보여 준다
// onAgent가 있으면 헤더에 '상담원 연결' 버튼 (국내 전용 — 외국어 답변 중에는 App이 넘기지 않음)
export function ChatView({ turns, onBack, onAgent }: { turns: ChatTurn[]; onBack: () => void; onAgent?: () => void }) {
  const end = useRef<HTMLDivElement>(null);

  // 새 질문·답변이 오면 맨 아래로
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <button type="button" className={styles.iconBtn} onClick={onBack} aria-label="뒤로">
          <Icon name="back" size={20} strokeWidth={2.2} />
        </button>
        <h1>AI 상담</h1>
        {onAgent && (
          <button type="button" className={styles.agentBtn} onClick={onAgent}>
            <Icon name="headset" size={16} /> 상담원 연결
          </button>
        )}
      </header>
      <div className={styles.list} aria-live="polite">
        {turns.map((t) => (
          <section key={t.id} className={styles.turn}>
            <p className={styles.question}>{t.question}</p>
            {t.status === 'loading' && (
              <p className={`${styles.answer} ${styles.loading}`} aria-label="답변을 준비하고 있어요">
                <span /><span /><span />
              </p>
            )}
            {t.status === 'error' && (
              <p className={`${styles.answer} ${styles.error}`}>{t.error}</p>
            )}
            {t.status === 'done' && t.res && (
              <>
                {t.res.emergency && (
                  <div className={styles.emergency} role="alert">
                    <p><Icon name="alert" size={16} strokeWidth={2.2} /> {t.res.emergency}</p>
                    <a href="tel:119">119 전화</a>
                  </div>
                )}
                <div className={styles.answer}>
                  <p className={styles.text}>{t.res.answer}</p>
                  {t.res.translated_notice && <p className={styles.notice}>{t.res.translated_notice}</p>}
                  {t.res.sources.length > 0 && (
                    <ul className={styles.sources} aria-label="참고한 홈페이지 내용">
                      {t.res.sources.slice(0, 3).map((s) => (
                        <li key={`${s.title}-${s.source_url}`}>
                          {s.source_url
                            ? <a href={s.source_url} target="_blank" rel="noopener noreferrer">{sourceLabel(t.res!.lang, s.title)}</a>
                            : <span>{sourceLabel(t.res!.lang, s.title)}</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </section>
        ))}
        <div ref={end} />
      </div>
    </div>
  );
}
