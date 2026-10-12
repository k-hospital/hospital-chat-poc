import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // GitHub Pages 배포용 기본 경로 설정 (저장소 이름)
  base: '/hospital-chat-poc/', 
  
  build: {
    // 결과물을 frontend 폴더 바깥(상위)의 production-site 폴더로 지정
    outDir: '../production-site',
    // 빌드할 때마다 기존 결과물 폴더를 깨끗하게 비워줌
    emptyOutDir: true, 
  }
});
