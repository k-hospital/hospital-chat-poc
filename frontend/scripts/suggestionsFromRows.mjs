// 추천 질문 엑셀(frontend/data/suggestions.xlsx)의 행 → suggestions.json 변환 (순수 함수, 파일 입출력 없음).
// 엑셀 형식: '추천질문' 시트(질문·화면·연결 기능·순서·사용) + '목록' 시트(화면/연결 기능 선택지와 내부 키).
// 읽기·쓰기는 sync-suggestions.mjs가 맡고, 여기서는 검증과 변환만 한다 (suggestionsFromRows.test.mjs).

export const QUESTION_HEADERS = ['질문', '화면', '연결 기능', '순서', '사용'];
export const STATUS_ON = '사용';
export const STATUS_OFF = '중지';

const text = (v) => (v === null || v === undefined ? '' : String(v).trim());
// 띄어쓰기만 다른 같은 질문을 중복으로 본다
const squash = (s) => s.replace(/\s+/g, '');

// '목록' 시트: 1행은 머리글, 화면은 A·B열(이름·내부 키), 연결 기능은 D·E열.
// '※'로 시작하는 안내 문구 줄은 건너뛴다.
export function parseOptionLists(rows) {
  const errors = [];
  const screens = new Map();
  const features = new Map();

  const read = (map, nameCol, keyCol, kind) => {
    rows.slice(1).forEach((row, i) => {
      const name = text(row[nameCol]);
      const key = text(row[keyCol]);
      if (!name || name.startsWith('※')) return;
      const line = i + 2;
      if (!key) return errors.push(`'목록' 시트 ${line}행: ${kind} '${name}'의 내부 키가 비어 있습니다`);
      if (map.has(name)) return errors.push(`'목록' 시트 ${line}행: ${kind} '${name}'이(가) 중복됩니다`);
      map.set(name, key);
    });
  };
  read(screens, 0, 1, '화면');
  read(features, 3, 4, '연결 기능');

  if (screens.size === 0) errors.push("'목록' 시트에 화면이 하나도 없습니다");
  if (features.size === 0) errors.push("'목록' 시트에 연결 기능이 하나도 없습니다");
  return { screens, features, errors };
}

// 반환: { data: { screens: { <화면 키>: [{ text, intent, label }] } } | null, errors: string[] }
export function buildSuggestions(questionRows, listRows) {
  const lists = parseOptionLists(listRows);
  const errors = [...lists.errors];

  const header = (questionRows[0] ?? []).slice(0, QUESTION_HEADERS.length).map(text);
  if (QUESTION_HEADERS.some((h, i) => header[i] !== h)) {
    errors.push(`'추천질문' 시트 1행 머리글은 "${QUESTION_HEADERS.join(' / ')}" 이어야 합니다 (지금: "${header.join(' / ')}")`);
  }
  if (errors.length > 0) return { data: null, errors };

  const items = [];
  const seen = new Set();
  questionRows.slice(1).forEach((row, i) => {
    const line = i + 2;
    const [q, screenName, featureName, orderRaw, status] = QUESTION_HEADERS.map((_, c) => text(row[c]));
    if (!q && !screenName && !featureName && !orderRaw && !status) return; // 빈 줄

    const problems = [];
    if (!q) problems.push('질문이 비어 있습니다');
    if (!screenName) problems.push('화면이 비어 있습니다');
    else if (!lists.screens.has(screenName)) problems.push(`화면 '${screenName}'이(가) '목록' 시트에 없습니다`);
    if (!featureName) problems.push('연결 기능이 비어 있습니다');
    else if (!lists.features.has(featureName)) problems.push(`연결 기능 '${featureName}'이(가) '목록' 시트에 없습니다`);
    const order = Number(orderRaw);
    if (!orderRaw || !Number.isInteger(order) || order < 1) problems.push(`순서는 1 이상의 정수여야 합니다 (지금: '${orderRaw}')`);
    if (status !== STATUS_ON && status !== STATUS_OFF) problems.push(`사용 칸은 '${STATUS_ON}' 또는 '${STATUS_OFF}'이어야 합니다 (지금: '${status}')`);
    if (problems.length > 0) {
      errors.push(...problems.map((p) => `'추천질문' 시트 ${line}행: ${p}`));
      return;
    }
    if (status === STATUS_OFF) return;

    const dupKey = `${screenName}\u0000${squash(q)}`;
    if (seen.has(dupKey)) {
      errors.push(`'추천질문' 시트 ${line}행: 화면 '${screenName}'에 같은 질문 '${q}'이(가) 이미 있습니다`);
      return;
    }
    seen.add(dupKey);
    items.push({ screenName, order, line, text: q, intent: lists.features.get(featureName), label: featureName });
  });
  if (errors.length > 0) return { data: null, errors };

  // 화면 순서는 '목록' 시트 순서, 화면 안에서는 순서 → 입력한 줄 순
  const screens = {};
  for (const [screenName, screenKey] of lists.screens) {
    const list = items
      .filter((it) => it.screenName === screenName)
      .sort((a, b) => a.order - b.order || a.line - b.line)
      .map(({ text: t, intent, label }) => ({ text: t, intent, label }));
    if (list.length > 0) screens[screenKey] = list;
  }
  if (Object.keys(screens).length === 0) {
    return { data: null, errors: ["'사용'으로 표시된 추천 질문이 하나도 없습니다"] };
  }
  return { data: { screens }, errors: [] };
}
