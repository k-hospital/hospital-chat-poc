import { Icon } from '../home/icons';
import styles from './PageViewer.module.css';

// 등록된 연결 주소를 챗봇 화면 안에서 보여줌 (뒤로 가기 시 메인으로 복귀)
// 외부 사이트가 iframe 표시를 막는 경우를 대비해 "새 창" 버튼 제공
export function PageViewer({ url, title, onBack }: { url: string; title: string; onBack: () => void }) {
  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <button type="button" className={styles.iconBtn} onClick={onBack} aria-label="뒤로">
          <Icon name="back" size={20} strokeWidth={2.2} />
        </button>
        <h1>{title}</h1>
        <a className={styles.newTab} href={url} target="_blank" rel="noopener noreferrer">새 창</a>
      </header>
      <iframe className={styles.frame} src={url} title={title} />
    </div>
  );
}
