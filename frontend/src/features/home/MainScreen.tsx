import { useState, type FormEvent } from 'react';
import { Icon } from './icons';
import type { ChatConfig, MainScreenHandlers, MenuItem } from './types';
import styles from './MainScreen.module.css';

const DEFAULT_DISCLAIMER = 'AI 안내는 참고용이며 진단이 아닙니다';

const byOrder = (items: MenuItem[]) =>
  items.filter((i) => i.visible).sort((a, b) => a.order - b.order);

export function MainScreen({ config, handlers }: { config: ChatConfig; handlers: MainScreenHandlers }) {
  const [text, setText] = useState('');
  const day = config.isOperatingHours;
  const tiles = byOrder(config.tiles);
  const faqs = byOrder(config.faqs);
  // 면책 문구는 관리자가 비워도 기본 문구로 강제 노출
  const disclaimer = config.disclaimer?.trim() || DEFAULT_DISCLAIMER;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    handlers.onSendText(t);
    setText('');
  };

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.hospital}>{config.hospitalName}</span>
          <span className={styles.badge}>AI 상담</span>
        </div>
        {day ? (
          <button type="button" className={styles.agentBtn} onClick={handlers.onAgent}>
            <Icon name="headset" size={16} strokeWidth={2} /> 상담원 연결
          </button>
        ) : (
          <button type="button" className={styles.agentBtn} onClick={handlers.onCallback}>
            <Icon name="phone" size={16} strokeWidth={2} /> 콜백 요청
          </button>
        )}
      </header>

      <main className={styles.body}>
        <div className={styles.greeting}>
          <h1>무엇을 도와드릴까요?</h1>
          <p>{day ? '진료 예약부터 오시는 길까지 안내해 드려요' : '상담원 운영시간 외에도 AI가 안내해 드려요'}</p>
        </div>

        {day ? (
          <button type="button" className={styles.hero}
            onClick={() => handlers.onAction({ intent: config.hero.intent, label: config.hero.title, requiresAuth: false })}>
            <span className={styles.heroText}>
              <span className={styles.heroEyebrow}>{config.hero.eyebrow}</span>
              <span className={styles.heroTitle}>{config.hero.title}</span>
              <span className={styles.heroDesc}>{config.hero.description}</span>
              <span className={styles.heroCta}>{config.hero.ctaLabel} <Icon name="arrow" size={14} strokeWidth={2.4} /></span>
            </span>
            <span className={styles.heroIcon}><Icon name="calendar" size={40} strokeWidth={1.6} /></span>
          </button>
        ) : (
          <section className={styles.night} aria-label="운영시간 안내">
            <div className={styles.nightHead}><Icon name="moon" size={22} /> 지금은 상담원 운영시간이 아니에요</div>
            <p>상담원 운영: {config.operatingHoursText}<br />예약 · 안내는 지금도 AI로 이용할 수 있고,<br />상담원 문의는 콜백으로 접수돼요.</p>
            <button type="button" onClick={handlers.onCallback}>상담원 콜백 요청하기</button>
          </section>
        )}

        <div className={day ? styles.tiles : styles.tilesCompact}>
          {(day ? tiles : [{ ...config.hero, id: 'hero', label: config.hero.title, icon: 'calendar' as const, requiresAuth: false, order: 0, visible: true }, ...tiles.slice(0, 3)])
            .map((t) => (
              <button key={t.id} type="button" className={styles.tile}
                onClick={() => handlers.onAction({ intent: t.intent, label: t.label, requiresAuth: t.requiresAuth })}>
                <span className={styles.tileIcon}><Icon name={t.icon} /></span>
                <span className={styles.tileText}>
                  <span className={styles.tileLabel}>{t.label}</span>
                  {day && 'description' in t && t.description && <span className={styles.tileDesc}>{t.description}</span>}
                </span>
              </button>
            ))}
        </div>

        {day ? (
          <div className={styles.faq}>
            <span className={styles.faqTitle}>자주 찾는 질문</span>
            <div className={styles.chips}>
              {faqs.map((f) => (
                <button key={f.id} type="button" className={styles.chip}
                  onClick={() => handlers.onAction({ intent: f.intent, label: f.label, requiresAuth: f.requiresAuth })}>
                  {f.label}
                  {f.requiresAuth && <Icon name="lock" size={13} strokeWidth={2.2} className={styles.lock} />}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className={styles.emergency} role="note">
            <Icon name="alert" size={22} strokeWidth={2} className={styles.emergencyIcon} />
            <div>
              <strong>응급 상황이신가요?</strong>
              <span>119 또는 응급실로 즉시 연락하세요</span>
            </div>
            <a href="tel:119">119 전화</a>
          </div>
        )}
      </main>

      <footer className={styles.footer}>
        <p className={styles.disclaimer}><Icon name="info" size={13} strokeWidth={2} /> {disclaimer}</p>
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
    </div>
  );
}
