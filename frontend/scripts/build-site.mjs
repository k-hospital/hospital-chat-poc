// 메인 화면(site/) + 챗봇(/chat/) + 연결 페이지(/pages/)를 Netlify에 그대로 올릴 폴더 하나로 묶는다.
//   npm run build:site                       → <저장소>/deploy
//   npm run build:site -- --out <폴더 경로>  → 지정한 폴더
// 결과 폴더를 Netlify 사이트의 "배포" 화면에 끌어다 놓으면 된다.
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'vite';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repo = resolve(frontend, '..');

const outArg = process.argv.indexOf('--out');
const out = outArg > -1 && process.argv[outArg + 1] ? resolve(process.argv[outArg + 1]) : join(repo, 'deploy');

// 저장소 루트나 소스 폴더를 지우는 실수를 막는다
if (out === repo || out === frontend || out === join(repo, 'site')) {
  throw new Error(`출력 폴더로 쓸 수 없는 경로입니다: ${out}`);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(join(out, 'pages'), { recursive: true });

// 챗봇: /chat/ 경로 기준으로 빌드 (경로 변환 문제를 피하려고 Vite API로 직접 호출)
await build({ root: frontend, base: '/chat/', logLevel: 'warn', build: { outDir: join(out, 'chat'), emptyOutDir: true } });

// 메인 화면: 사이트 첫 화면
cpSync(join(repo, 'site', 'index.html'), join(out, 'index.html'));

// 연결 페이지: 챗봇이 /pages/... 경로로 여는 페이지들
const pages = join(frontend, 'public', 'pages');
if (existsSync(pages)) {
  for (const name of readdirSync(pages)) cpSync(join(pages, name), join(out, 'pages', name), { recursive: true });
}

console.log(`배포 폴더 생성 완료: ${out}`);
