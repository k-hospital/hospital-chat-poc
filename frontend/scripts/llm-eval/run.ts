// 질문 분류용 LLM 비교 평가 (읽기 전용: 사내 모델 서버에 분류 요청만 보낸다).
//   cd frontend
//   npx vite-node scripts/llm-eval/run.ts                                 # 기본: models.local.json 의 모델(skipByDefault 제외) 전체 문항
//   npx vite-node scripts/llm-eval/run.ts -- --models <키> --limit 5      # 연결 확인(5문항)
// 모델 서버 주소·이름은 사내 정보라 저장소에 두지 않는다: models.example.json 을 models.local.json 으로 복사해 채운다.
// 정답이 붙은 문항(cases.json)을 모델마다 한 건씩 순서대로 보내 정확도·형식 오류·응답 시간을 잰다.
// 프롬프트와 출력 스키마는 백엔드가 쓰는 파일(backend/app/features/chat/)을 그대로 읽는다.
// 정답 기준: 질문이 한 가지면 기능 1개, 복합 질문(k: "multi")이면 말한 순서대로 정해 둔 목록과 같아야 한다.
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { routeQuestion } from '../../src/shared/chat/intentRouter';

const here = dirname(fileURLToPath(import.meta.url));
const chatDir = resolve(here, '../../../backend/app/features/chat');
const PROMPT = readFileSync(join(chatDir, 'intent_prompt.txt'), 'utf8').trim();
const SCHEMA = JSON.parse(readFileSync(join(chatDir, 'intent_schema.json'), 'utf8')) as {
  properties: { intents: { maxItems: number; items: { properties: { intent: { enum: string[] }; topic: { enum: string[] } } } } };
};
const ITEM = SCHEMA.properties.intents.items.properties;
const INTENTS = new Set(ITEM.intent.enum);
const TOPICS = new Set(ITEM.topic.enum);
const MAX_INTENTS = SCHEMA.properties.intents.maxItems;
const TOPIC_INTENTS = new Set(['symptom.guide', 'info.directions']);

interface Expect { i: string; p: string }
interface Case { t: string; i: string; p: string; k: string; x?: Expect[] }
interface ModelDef { label: string; base: string; model: string; extra: Record<string, unknown> }
interface Pred { intent: string; topic: string }

const CASES: Case[] = JSON.parse(readFileSync(join(here, 'cases.json'), 'utf8'));
const expectedOf = (c: Case): Expect[] => c.x ?? [{ i: c.i, p: c.p }];

// 분류에는 "생각하는 모드"가 필요 없다 — noThink 모델은 enable_thinking=false 로 끈다
const NO_THINK = { chat_template_kwargs: { enable_thinking: false } };
interface ModelFile { label: string; base: string; model: string; noThink?: boolean; skipByDefault?: boolean }
let modelFile: Record<string, ModelFile>;
try {
  modelFile = JSON.parse(readFileSync(join(here, 'models.local.json'), 'utf8'));
} catch {
  throw new Error('models.local.json 이 없습니다. models.example.json 을 복사해 사내 서버 주소와 모델 이름을 채우세요 (저장소에 올라가지 않는 파일입니다)');
}
const MODELS: Record<string, ModelDef> = Object.fromEntries(
  Object.entries(modelFile).map(([key, m]) => [key, { label: m.label, base: m.base, model: m.model, extra: m.noThink ? NO_THINK : {} }]),
);
const DEFAULT_KEYS = Object.keys(modelFile).filter((k) => !modelFile[k].skipByDefault);

const args = process.argv.slice(2);
const arg = (name: string) => {
  const i = args.indexOf(`--${name}`);
  return i > -1 ? args[i + 1] : undefined;
};
const modelKeys = arg('models') ? arg('models')!.split(',').map((s) => s.trim()).filter(Boolean) : DEFAULT_KEYS;
const limit = Number(arg('limit') ?? CASES.length);
const cases = CASES.slice(0, limit);

for (const k of modelKeys) if (!MODELS[k]) throw new Error(`알 수 없는 모델: ${k} (가능: ${Object.keys(MODELS).join(', ')})`);

// 백엔드 service.normalize 와 같은 규칙으로 정리: 모르는 값 제거, 중복 제거, 응급 우선, unknown 은 단독일 때만
const parsePreds = (content: string): Pred[] | null => {
  const text = content.trim().replace(/^```(?:json)?\s*|\s*```$/g, '');
  try {
    const o = JSON.parse(text) as { intents?: { intent?: unknown; topic?: unknown }[] };
    if (!Array.isArray(o.intents)) return null;
    const out: Pred[] = [];
    for (const it of o.intents) {
      const intent = String(it?.intent ?? '');
      if (!INTENTS.has(intent)) continue;
      const t = String(it?.topic ?? 'none');
      const topic = TOPIC_INTENTS.has(intent) && TOPICS.has(t) ? t : 'none';
      if (!out.some((p) => p.intent === intent && p.topic === topic)) out.push({ intent, topic });
    }
    if (out.length === 0) return null;
    const em = out.find((p) => p.intent === 'emergency');
    if (em) return [em];
    const known = out.filter((p) => p.intent !== 'unknown');
    return (known.length > 0 ? known : out).slice(0, MAX_INTENTS);
  } catch {
    return null;
  }
};

interface CallResult { preds: Pred[] | null; ms: number; error?: string }

async function classify(m: ModelDef, text: string): Promise<CallResult> {
  const body = {
    model: m.model, temperature: 0, max_tokens: 120,
    messages: [{ role: 'system', content: PROMPT }, { role: 'user', content: text }],
    response_format: { type: 'json_schema', json_schema: { name: 'intents', strict: true, schema: SCHEMA } },
    ...m.extra,
  };
  const t0 = performance.now();
  try {
    const res = await fetch(`${m.base}/chat/completions`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body), signal: AbortSignal.timeout(30000),
    });
    if (!res.ok) return { preds: null, ms: performance.now() - t0, error: `HTTP ${res.status} ${(await res.text()).slice(0, 120)}` };
    const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content ?? '';
    const preds = parsePreds(content);
    return { preds, ms: performance.now() - t0, error: preds ? undefined : `형식 오류: ${content.slice(0, 80)}` };
  } catch (err) {
    return { preds: null, ms: performance.now() - t0, error: err instanceof Error ? err.message : String(err) };
  }
}

// 현재 규칙 판별기 결과를 같은 형식으로 (규칙은 항상 기능 1개)
const ruleOf = (text: string): { preds: Pred[]; hit: boolean } => {
  const r = routeQuestion(text);
  if (r.kind === 'emergency') return { preds: [{ intent: 'emergency', topic: 'none' }], hit: true };
  if (r.kind === 'unknown') return { preds: [{ intent: 'unknown', topic: 'none' }], hit: false };
  return { preds: [{ intent: r.intent, topic: r.topic ?? 'none' }], hit: true };
};

const sameItem = (p: Pred, e: Expect) => p.intent === e.i && (!TOPIC_INTENTS.has(e.i) || p.topic === e.p);
const correct = (c: Case, preds: Pred[] | null) => {
  if (preds === null) return false;
  const exp = expectedOf(c);
  return preds.length === exp.length && exp.every((e, i) => sameItem(preds[i], e));
};
const show = (ps: Pred[] | null, fallback = '실패') =>
  ps ? ps.map((p) => (TOPIC_INTENTS.has(p.intent) ? `${p.intent}/${p.topic}` : p.intent)).join(' + ') : fallback;

const pct = (n: number, d: number) => (d === 0 ? '  -  ' : `${((n / d) * 100).toFixed(1)}%`.padStart(6));
const quantile = (xs: number[], q: number) => {
  if (xs.length === 0) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * s.length))];
};
const KINDS = ['direct', 'colloquial', 'multi', 'emergency', 'oos', 'trap'] as const;
const KIND_LABEL: Record<string, string> = { direct: '직접', colloquial: '구어체', multi: '복합', emergency: '응급', oos: '무관', trap: '함정' };

const rules = cases.map((c) => ruleOf(c.t));
const summary: Record<string, unknown> = {};
const lines: string[] = [];
const log = (s = '') => { lines.push(s); console.log(s); };

const count = (k: string) => cases.filter((c) => c.k === k).length;
log(`평가 문항 ${cases.length}개 (${KINDS.map((k) => `${KIND_LABEL[k]} ${count(k)}`).join(' / ')})`);
log('정답 기준: 기능(intent)과 말한 순서가 같고, 증상·오시는 길은 주제(topic)도 같아야 정답');
log();

const header = ['', '전체', ...KINDS.map((k) => KIND_LABEL[k])];
const row = (name: string, oks: boolean[]) => [
  name.padEnd(30),
  pct(oks.filter(Boolean).length, oks.length),
  ...KINDS.map((k) => {
    const idx = cases.map((c, i) => (c.k === k ? i : -1)).filter((i) => i >= 0);
    return pct(idx.filter((i) => oks[i]).length, idx.length);
  }),
].join(' ');
const results: Record<string, { c: Case; res: CallResult }[]> = {};

for (const key of modelKeys) {
  const m = MODELS[key];
  log(`▶ ${m.label} 평가 중... (${cases.length}건, 순서대로 1건씩)`);
  const out: { c: Case; res: CallResult }[] = [];
  for (const c of cases) {
    out.push({ c, res: await classify(m, c.t) });
    if (out.length % 20 === 0) log(`   ${out.length}/${cases.length}`);
  }
  results[key] = out;
}

log();
log(`${header[0].padEnd(30)} ${header.slice(1).map((h) => h.padStart(6)).join(' ')}`);
const ruleOk = cases.map((c, i) => correct(c, rules[i].preds));
log(row('현재 규칙만', ruleOk));
for (const key of modelKeys) {
  const out = results[key];
  const llmOk = out.map(({ c, res }) => correct(c, res.preds));
  log(row(`${MODELS[key].label} 단독`, llmOk));
  summary[key] = { llm: llmOk.filter(Boolean).length, total: llmOk.length };
}
log();
log('모델별 안정성·속도');
log(`${'모델'.padEnd(26)} 형식오류  응급재현  응급오탐  평균ms  p50ms  p95ms`);
for (const key of modelKeys) {
  const out = results[key];
  const bad = out.filter((o) => o.res.preds === null).length;
  const em = out.filter((o) => o.c.k === 'emergency');
  const emHit = em.filter((o) => o.res.preds?.[0]?.intent === 'emergency').length;
  const falseEm = out.filter((o) => o.c.i !== 'emergency' && o.res.preds?.some((p) => p.intent === 'emergency')).length;
  const ms = out.map((o) => o.res.ms);
  const mean = ms.reduce((a, b) => a + b, 0) / Math.max(ms.length, 1);
  log(`${MODELS[key].label.padEnd(26)} ${String(bad).padStart(7)}  ${`${emHit}/${em.length}`.padStart(7)}  ${String(falseEm).padStart(7)}  ${mean.toFixed(0).padStart(6)} ${quantile(ms, 0.5).toFixed(0).padStart(6)} ${quantile(ms, 0.95).toFixed(0).padStart(6)}`);
  Object.assign(summary[key] as object, { invalid: bad, emergencyHit: emHit, emergencyTotal: em.length, falseEmergency: falseEm, meanMs: Math.round(mean) });
}

log();
log('오답 목록 (모델 단독, 최대 15건씩)');
for (const key of modelKeys) {
  const wrong = results[key].filter(({ c, res }) => !correct(c, res.preds));
  log(`■ ${MODELS[key].label}: ${wrong.length}건 오답`);
  for (const { c, res } of wrong.slice(0, 15)) {
    const exp = expectedOf(c).map((e) => (TOPIC_INTENTS.has(e.i) ? `${e.i}/${e.p}` : e.i)).join(' + ');
    log(`   - "${c.t}"  정답 ${exp} → 예측 ${show(res.preds, `(${res.error ?? '실패'})`)}`);
  }
}

const dir = join(here, 'results');
mkdirSync(dir, { recursive: true });
const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
const file = join(dir, `eval-${stamp}.json`);
writeFileSync(file, JSON.stringify({
  at: new Date().toISOString(), models: modelKeys, cases: cases.length, summary,
  detail: Object.fromEntries(modelKeys.map((k) => [k, results[k].map(({ c, res }) => ({
    text: c.t, expect: expectedOf(c), kind: c.k, got: res.preds, ms: Math.round(res.ms), error: res.error,
  }))])),
}, null, 2), 'utf8');
log();
log(`결과 저장: ${file}`);
