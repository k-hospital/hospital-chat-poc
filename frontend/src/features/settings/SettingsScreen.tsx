import { useMemo, useState, type FormEvent } from 'react';
import { Icon } from '../home/icons';
import type { ChatConfig } from '../home/types';
import { AGENT_KEY, CALLBACK_KEY, isValidUrl, type LinkMap } from './linkStore';
import styles from './SettingsScreen.module.css';

interface Row { key: string; label: string; hint: string }
interface Group { title: string; rows: Row[] }

const byOrder = <T extends { order: number }>(items: T[]) => [...items].sort((a, b) => a.order - b.order);

export function SettingsScreen({ config, links, onSave, onBack }: {
  config: ChatConfig;
  links: LinkMap;
  onSave: (links: LinkMap) => boolean;
  onBack: () => void;
}) {
  const [draft, setDraft] = useState<LinkMap>(links);
  const [touched, setTouched] = useState(false);
  const [saved, setSaved] = useState<'ok' | 'fail' | null>(null);

  const groups: Group[] = useMemo(() => [
    {
      title: '메인 메뉴',
      rows: [
        { key: config.hero.intent, label: config.hero.title, hint: '큰 배너' },
        ...byOrder(config.tiles).map((t) => ({ key: t.intent, label: t.label, hint: '메뉴 타일' })),
      ],
    },
    {
      title: '자주 찾는 질문',
      rows: byOrder(config.faqs).map((f) => ({ key: f.intent, label: f.label, hint: f.requiresAuth ? '인증 필요' : '질문 칩' })),
    },
    {
      title: '상담',
      rows: [
        { key: AGENT_KEY, label: '상담원 연결', hint: '운영시간' },
        { key: CALLBACK_KEY, label: '콜백 요청', hint: '운영시간 외' },
      ],
    },
  ], [config]);

  const errors = Object.fromEntries(
    Object.entries(draft).filter(([, v]) => v.trim() && !isValidUrl(v.trim())).map(([k]) => [k, true]),
  );
  const hasError = Object.keys(errors).length > 0;

  const change = (key: string, value: string) => {
    setDraft((d) => ({ ...d, [key]: value }));
    setTouched(true);
    setSaved(null);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (hasError) return;
    const clean = Object.fromEntries(
      Object.entries(draft).map(([k, v]) => [k, v.trim()] as const).filter(([, v]) => v),
    );
    const ok = onSave(clean);
    setSaved(ok ? 'ok' : 'fail');
    if (ok) setTouched(false);
  };

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <button type="button" className={styles.backBtn} onClick={onBack} aria-label="뒤로">
          <Icon name="back" size={20} strokeWidth={2.2} />
        </button>
        <h1>기능별 연결 주소</h1>
      </header>

      <form className={styles.form} onSubmit={submit} noValidate>
        <p className={styles.intro}>
          버튼을 눌렀을 때 챗봇 안에서 열릴 주소를 등록하세요. 비워 두면 '준비중'으로 표시됩니다.
        </p>

        {groups.map((g) => (
          <section key={g.title} className={styles.group}>
            <h2>{g.title}</h2>
            {g.rows.map((r) => {
              const id = `link-${r.key}`;
              const value = draft[r.key] ?? '';
              return (
                <div key={r.key} className={styles.row}>
                  <label htmlFor={id} className={styles.rowHead}>
                    <span className={styles.label}>{r.label}</span>
                    <span className={styles.hint}>{r.hint} · {r.key}</span>
                  </label>
                  <div className={styles.inputWrap}>
                    <input id={id} type="text" inputMode="url" placeholder="https:// 또는 /pages/..."
                      value={value} onChange={(e) => change(r.key, e.target.value)}
                      aria-invalid={errors[r.key] ? true : undefined} autoComplete="off" />
                    {value && (
                      <button type="button" className={styles.clearBtn} onClick={() => change(r.key, '')} aria-label={`${r.label} 주소 지우기`}>✕</button>
                    )}
                  </div>
                  {errors[r.key] && <p className={styles.error}>https:// 주소 또는 / 로 시작하는 경로를 입력하세요</p>}
                </div>
              );
            })}
          </section>
        ))}

        <div className={styles.actions}>
          {saved === 'ok' && <span className={styles.savedMsg} role="status">저장되었습니다</span>}
          {saved === 'fail' && <span className={styles.failMsg} role="alert">저장하지 못했습니다 (브라우저 저장소 차단)</span>}
          <button type="submit" className={styles.saveBtn} disabled={hasError || !touched}>저장</button>
        </div>
      </form>
    </div>
  );
}
