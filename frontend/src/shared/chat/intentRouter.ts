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
// 놓치는 것(미탐)이 불필요한 119 안내(오탐)보다 훨씬 위험하므로 부사·조사·어순이 달라도 잡도록 넓게 둔다.
// 단, 일상 표현과 겹치는 말("숨은 맛집", "정신이 없어요", "다리에 힘이 없어요")은 걸리지 않게 문맥을 함께 본다.
// 의료진 검수를 받기 전의 목록이다 — 확정 전에는 항목을 줄이지 말고 늘리기만 한다.
const EMERGENCY: RegExp[] = [
  // 가슴·심장: 통증, 조임, 압박 ("가슴이 너무 아파요", "가슴을 쥐어짜는 것 같아요")
  /(가슴|심장|흉부).{0,10}(아파|아프|아픈|통증|답답|조여|조이|쥐어|짓눌|눌리|압박|찢어|멎|멈출)/,
  /흉통/,
  // 호흡: "숨이 너무 차요", "숨을 못 쉬겠어요", "숨쉬기가 너무 힘들어요" ('숨은'처럼 조사가 다른 말은 제외)
  /숨\s*(이|을|도)?\s*(너무|많이|잘|제대로|갑자기|자꾸|계속)?\s*(차|막혀|막히|막힐|못\s*쉬|안\s*쉬|쉴\s*수\s*없|가빠|가쁘|헐떡)/,
  /숨\s*쉬(기|는\s*게|는\s*것)\s*(가|도)?\s*(너무|많이|갑자기)?\s*(힘들|어려|곤란|불편|버거)/,
  /호흡\s*(이|을)?\s*(곤란|힘들|어려|안\s*돼|못)/,
  /질식/,
  // 의식: 의식 저하, 실신, 쓰러짐 ('정신이 없어요'는 바쁘다는 뜻이라 제외)
  /의식\s*(이|을|도)?\s*(없|잃|흐려|흐릿|희미|혼미|저하|불명)/,
  /정신\s*(을)?\s*(잃|못\s*차려)|정신이\s*(혼미|흐려|오락가락)/,
  /기절|실신|혼절|졸도|까무러/,
  /쓰러(졌|져|지|질|진)/,
  // 출혈: "피가 계속 나는데 멈추질 않아요", "피가 많이 나요"
  /피\s*를?\s*토|토혈|각혈|하혈/,
  /(피|출혈).{0,10}(멈추(지|질)|안\s*멈|그치지|멎지|멎질)/,
  /피\s*(가|를)?\s*(많이|계속|너무|왈칵|콸콸)\s*(나|흘|쏟)/,
  /심한\s*출혈|출혈이\s*(심|많|멈)/,
  // 신경: 마비·경련·발작, 뇌졸중 의심 (갑작스러운 힘 빠짐·시야 이상·말이 어눌함·입이 돌아감)
  /마비|경련|발작/,
  /거품을?\s*물/,
  /갑자기.{0,14}(힘이\s*(안|없|빠|풀)|감각이\s*(없|안)|말이\s*(어눌|안)|발음|안\s*보|시야)/,
  /말이\s*(어눌|꼬|잘\s*안\s*나)|입(이|술이)\s*(돌아|한쪽)|얼굴이\s*(한쪽|돌아|처져)/,
  // 아래는 의료진 검수 전 임시 항목: 자해, 중독·과다 복용, 알레르기 쇼크, 임신 중 출혈
  /자살|자해|죽고\s*싶|목숨을\s*끊|극단적\s*선택/,
  /과다\s*복용|농약|독극물|락스를?\s*(마|먹)/,
  /아나필락시스/,
  /임신.{0,12}(출혈|피\s*가?\s*(나|비치)|하혈)/,
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

// 추천 질문을 눌렀을 때: 엑셀에서 정한 기능(intent)이 우선이다. 키워드 판별기가 못 알아보는 질문
// (예: "상담원연결")도 정해 둔 기능으로 이동한다. 응급 신호는 이 경우에도 가장 먼저 검사한다.
export function routeSuggestion(text: string, intent: string, label: string): RouteResult {
  const q = text.trim();
  if (EMERGENCY.some((p) => p.test(q))) return { kind: 'emergency' };
  const routed = routeQuestion(q);
  // 판별기도 같은 기능으로 봤다면 그쪽의 안내 문구와 주제(topic: 지하철·소화기 등)를 그대로 쓴다
  if (routed.kind === 'intent' && routed.intent === intent) return routed;
  return { kind: 'intent', intent, label, reply: `${label}(으)로 이동할게요` };
}
