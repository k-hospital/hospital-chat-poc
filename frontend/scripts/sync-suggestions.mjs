// 추천 질문 엑셀 → src/shared/chat/suggestions.json 생성.
//   npm run sync:suggestions                 (기본: data/suggestions.xlsx)
//   npm run sync:suggestions -- <엑셀 경로>   (다른 위치의 엑셀을 읽을 때)
// 엑셀 형식과 검증 규칙은 suggestionsFromRows.mjs 참고. 오류가 있으면 파일을 쓰지 않고 종료한다.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import readExcelFile from 'read-excel-file/node';
import { buildSuggestions } from './suggestionsFromRows.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(process.argv[2] ?? resolve(root, 'data/suggestions.xlsx'));
const target = resolve(root, 'src/shared/chat/suggestions.json');

const fail = (lines) => {
  console.error(lines.join('\n'));
  process.exit(1);
};

let sheets;
try {
  sheets = await readExcelFile(source);
} catch (err) {
  fail([`엑셀 파일을 읽지 못했습니다: ${source}`, `  ${err instanceof Error ? err.message : err}`,
    '  (엑셀에서 열어 둔 채라면 저장하고 닫은 뒤 다시 실행해 보세요)']);
}

const find = (name) => sheets.find((s) => s.sheet === name)?.data;
const questionRows = find('추천질문');
const listRows = find('목록');
if (!questionRows || !listRows) {
  fail([`엑셀에 '추천질문'과 '목록' 시트가 모두 있어야 합니다 (찾은 시트: ${sheets.map((s) => s.sheet).join(', ')})`]);
}

const { data, errors } = buildSuggestions(questionRows, listRows);
if (!data) fail(['추천 질문을 만들지 못했습니다. 엑셀을 고친 뒤 다시 실행하세요.', ...errors.map((e) => `  - ${e}`)]);

mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, `${JSON.stringify(data, null, 2)}\n`, 'utf8');

console.log(`생성 완료: ${target}`);
for (const [screen, list] of Object.entries(data.screens)) {
  console.log(`  [${screen}] ${list.length}개`);
  list.forEach((s, i) => console.log(`    ${i + 1}. ${s.text}  →  ${s.label} (${s.intent})`));
}
