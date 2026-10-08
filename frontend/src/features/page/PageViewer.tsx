import { useRef } from 'react';
import { Icon } from '../../shared/ui/icons';
import styles from './PageViewer.module.css';

// 질문 입력으로 열렸을 때 함께 넘기는 내용
export interface PageQuery {
  text: string;
  topic?: string;
}

// 등록된 연결 주소를 챗봇 화면 안에서 보여줌 (뒤로 가기 시 메인으로 복귀)
// 외부 사이트가 iframe 표시를 막는 경우를 대비해 "새 창" 버튼 제공
export function PageViewer({ url, title, query, onBack }: {
  url: string; title: string; query?: PageQuery; onBack: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);

  // 입력 문구는 주소(?q=)에 넣지 않고 페이지가 열린 뒤 메시지로 전달 — 건강 정보가 주소·로그에 남지 않게.
  // 같은 사이트의 페이지에만 보내고, 외부 사이트에는 보내지 않는다.
  const deliver = () => {
    const target = frame.current?.contentWindow;
    if (!query || !target) return;
    const origin = new URL(url, location.href).origin;
    if (origin !== location.origin) return;
    target.postMessage({ type: 'chatpoc:query', text: query.text, topic: query.topic }, origin);
  };

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <button type="button" className={styles.iconBtn} onClick={onBack} aria-label="뒤로">
          <Icon name="back" size={20} strokeWidth={2.2} />
        </button>
        <h1>{title}</h1>
        <a className={styles.newTab} href={url} target="_blank" rel="noopener noreferrer">새 창</a>
      </header>
      {query && (
        <p className={styles.query}><span>입력하신 내용</span>{query.text}</p>
      )}
      <iframe ref={frame} className={styles.frame} src={url} title={title} onLoad={deliver} />
    </div>
  );
}
