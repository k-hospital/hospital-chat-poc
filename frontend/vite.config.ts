import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중 /v1 요청 전달 (위에서부터 먼저 맞는 규칙)
    //  - 팀 backend(8000): /v1/config, /v1/chat/messages
    //  - ai-backend(8100): 그 밖의 /v1 (/v1/chat, /v1/stt, /v1/handoff, /v1/agent, /v1/callbacks) — ws: 상담원 연결 WebSocket
    //  Windows에서 localhost가 IPv6(::1)로 풀리면 127.0.0.1로만 띄운 uvicorn에 닿지 않으므로 IP로 적는다
    proxy: {
      '/v1/config': 'http://127.0.0.1:8000',
      '/v1/chat/messages': 'http://127.0.0.1:8000',
      '/v1': { target: 'http://127.0.0.1:8100', ws: true },
    },
  },
});
