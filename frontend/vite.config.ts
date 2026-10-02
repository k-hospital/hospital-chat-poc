import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    // 개발 중 /v1 요청은 로컬 FastAPI(8000)로 전달
    proxy: { '/v1': 'http://localhost:8000' },
  },
});
