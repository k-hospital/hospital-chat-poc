// 질문 문장 → 기능(intent) 판별. POC 단계라 키워드 규칙으로 판별하고,
// 백엔드 AI(POST /v1/chat/messages)가 준비되면 routeQuestion 내부만 교체한다.

export type SymptomTopic = 'digestive' | 'headache' | 'respiratory';
// 오시는 길 화면의 탭 (지하철 / 버스 / 자가용)
export type DirectionsTopic = 'subway' | 'bus' | 'car';
export type Topic = SymptomTopic | DirectionsTopic;

export const SYMPTOM_INTENT = 'symptom.guide';

export type RouteResult =
  | { kind: 'emergency' }
  | { kind: 'intent'; intent: string; label: string; reply: string; topic?: Topic }
  | { kind: 'unknown' };

interface Rule {
  intent: string;
  label: string;
  reply: string;
  topic?: Topic;
  patterns: RegExp[];
}

// 응급 신호는 다른 규칙보다 먼저 검사한다 (이동하지 않고 119 안내)
const EMERGENCY: RegExp[] = [
  /가슴\s*(이|가)?\s*(아파|아프|통증|답답|조여)/,
  /흉통/,
  /숨\s*(이|을)?\s*(차|막혀|못\s*쉬|쉬기\s*힘들|가빠)/,
  /호흡\s*곤란/,
  /의식\s*(이|을)?\s*(없|잃|흐려)/,
  /기절|실신/,
  /피\s*를?\s*토|토혈|각혈/,
  /마비|경련|발작/,
  /피\s*가?\s*(멈추지|안\s*멈)|심한\s*출혈/,
];

// 위에서부터 먼저 맞는 규칙을 사용 (구체적인 규칙을 위에 둔다)
const RULES: Rule[] = [
  {
    intent: 'booking.lookup', label: '예약 조회',
    reply: '예약 조회 화면으로 이동할게요',
    patterns: [/예약\s*(조회|확인|내역|변경|취소)/],
  },
  {
    intent: 'booking.start', label: '진료 예약',
    reply: '진료 예약 화면으로 이동할게요',
    patterns: [/예약/],
  },
  {
    intent: SYMPTOM_INTENT, label: '증상별 진료 안내', topic: 'digestive',
    reply: '소화기 증상으로 보여요. 증상별 진료 안내로 이동할게요',
    patterns: [
      /배\s*(가|를|도|이)?\s*(너무|많이|좀|계속)?\s*(아파|아프|쓰려|쓰리|불편|더부룩|통증|살살)/,
      /배탈|복통|명치|속\s*(이)?\s*(쓰려|쓰리|안\s*좋|더부룩|메스꺼)|속쓰림/,
      /설사|변비|소화\s*(가|이)?\s*(안|불량)|구토|토할|체한|체했/,
    ],
  },
  {
    intent: SYMPTOM_INTENT, label: '증상별 진료 안내', topic: 'headache',
    reply: '두통 증상으로 보여요. 증상별 진료 안내로 이동할게요',
    patterns: [/머리\s*(가|도)?\s*(너무|많이|계속)?\s*(아파|아프|지끈|어지)|두통|편두통|어지러/],
  },
  {
    intent: SYMPTOM_INTENT, label: '증상별 진료 안내', topic: 'respiratory',
    reply: '호흡기 증상으로 보여요. 증상별 진료 안내로 이동할게요',
    patterns: [/기침|가래|목\s*(이)?\s*(아파|아프|따가)|인후통|콧물|코막힘|열\s*(이)?\s*(나|있)|감기|몸살/],
  },
  {
    intent: 'faq.parking', label: '주차 안내',
    reply: '주차 안내로 이동할게요',
    patterns: [/주차/],
  },
  // 교통수단을 말하면 오시는 길의 해당 탭으로 ('주차'는 위의 주차 안내가 먼저 잡는다)
  {
    intent: 'info.directions', label: '오시는 길', topic: 'subway',
    reply: '지하철로 오시는 길을 보여 드릴게요',
    patterns: [/지하철|전철|\d\s*호선|역에서/],
  },
  {
    intent: 'info.directions', label: '오시는 길', topic: 'bus',
    reply: '버스로 오시는 길을 보여 드릴게요',
    patterns: [/버스|정류장|노선/],
  },
  {
    intent: 'info.directions', label: '오시는 길', topic: 'car',
    reply: '자가용으로 오시는 길을 보여 드릴게요',
    patterns: [/자가용|차로|차\s*타고|운전|내비|고속도로/],
  },
  {
    intent: 'info.directions', label: '오시는 길',
    reply: '오시는 길로 이동할게요',
    patterns: [
      /오시는\s*길|오는\s*길|가는\s*길|찾아\s*(가|오)|위치|어디\s*(에|야|있)|주소|교통/,
      /어떻게\s*(가|와|오)|(가는|오는)\s*방법|(가|오)려면|길\s*(좀)?\s*알려/,
    ],
  },
  {
    intent: 'faq.hours', label: '진료 시간',
    reply: '진료 시간 안내로 이동할게요',
    patterns: [/진료\s*시간|운영\s*시간|몇\s*시|언제\s*(까지|부터)|주말|공휴일/],
  },
  {
    intent: 'faq.certificate', label: '증명서 발급',
    reply: '증명서 발급 안내로 이동할게요',
    patterns: [/증명서|진단서|소견서|서류\s*발급|영수증/],
  },
  {
    intent: 'doctor.search', label: '의료진 찾기',
    reply: '의료진 찾기로 이동할게요',
    patterns: [/의료진|의사|교수|선생님|전문의/],
  },
  {
    intent: 'info.outpatient', label: '외래 안내',
    reply: '외래 안내로 이동할게요',
    patterns: [/외래|접수|초진|재진/],
  },
  {
    intent: 'info.health', label: '건강 정보',
    reply: '건강 정보로 이동할게요',
    patterns: [/건강\s*정보|검사\s*안내|질환/],
  },
];

// 메뉴에 없지만 질문으로 열 수 있는 화면 — 설정 화면에서 연결 주소를 등록할 수 있게 노출
export const QUESTION_TARGETS: { intent: string; label: string }[] = [
  { intent: SYMPTOM_INTENT, label: '증상별 진료 안내' },
];

export function routeQuestion(text: string): RouteResult {
  const q = text.trim();
  if (!q) return { kind: 'unknown' };
  if (EMERGENCY.some((p) => p.test(q))) return { kind: 'emergency' };
  const rule = RULES.find((r) => r.patterns.some((p) => p.test(q)));
  if (!rule) return { kind: 'unknown' };
  const { intent, label, reply, topic } = rule;
  return topic ? { kind: 'intent', intent, label, reply, topic } : { kind: 'intent', intent, label, reply };
}
