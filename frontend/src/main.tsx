import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import AgentApp from './agent/AgentApp';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* 상담원 화면: .../agent 또는 ?agent — 같은 빌드에서 주소로 나눈다 */}
    {/\/agent\/?$/.test(location.pathname) || new URLSearchParams(location.search).has('agent') ? <AgentApp /> : <App />}
  </StrictMode>,
);
