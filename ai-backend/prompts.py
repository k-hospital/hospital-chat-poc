"""
프롬프트·언어별 문구 모음 — LLM에 보내는 내용은 모두 이 파일에서 만든다.
상세 설명·검증 이력: docs/프롬프트_정리.md

구성
  ① LANGS            언어별 설정 (이름, 답변 언어 지시, 고정 안내 문구, 오류 문구)
  ② EMERGENCY_KEYWORDS
  ③ LLM 프롬프트     EXPAND_V1, ANSWER_V5, REWRITE_LANG_V2 + 메시지 조립 함수

새 언어 추가: LANGS에 한 항목 + config.SUPPORTED_LANGS에 코드 추가.
고정 문구는 의료 안내라 최종 문구는 국제진료센터 검수 필요 (설계서 11장 6번).
"""

from __future__ import annotations

# =============================================================================
# ① 언어별 설정
# =============================================================================
# reply_rule   : 답변 언어 지시. 프롬프트 맨 끝에 그 언어로 한 번 더 넣는다 (ANSWER_V5).
# hospital_name: 답변에서 병원을 부르는 고정 명칭 (실행마다 번역이 달라지지 않게, ANSWER_V5)
LANGS: dict[str, dict] = {
    "en": {
        "name": "English",
        "hospital_name": "Catholic Kwandong University International St. Mary's Hospital",
        "reply_rule": "Answer in English only.",
        "disclaimer": "AI guidance is for reference only and is not a diagnosis.",
        "translated_notice": "This answer was machine-translated from Korean hospital information. "
                             "For accurate details, please contact the {center}.",
        "emergency": "If this is an emergency, call 119 or go to the emergency room right away.",
        "errors": {
            "EMPTY_MESSAGE": "Please enter a question.",
            "MESSAGE_TOO_LONG": "Your question is too long. Please keep it under {limit} characters.",
            "UNSUPPORTED_LANGUAGE": "This language is not supported yet.",
            "SERVICE_UNAVAILABLE": "Sorry, the service is temporarily unavailable. Please try again shortly.",
            "RATE_LIMITED": "Too many requests. Please wait a moment and try again.",
            "AUDIO_TOO_LARGE": "The recording is too long. Please keep it under {seconds} seconds.",
            "AUDIO_EMPTY": "No speech was recognized. Please try again.",
        },
    },
    "zh": {
        "name": "Simplified Chinese (简体中文)",
        "hospital_name": "国际圣母医院",   # 2026-10-06 사용자 지정
        "reply_rule": "Answer in Simplified Chinese only (simplified characters, never traditional). "
                      "请只用简体中文回答：只用简体字，不要使用繁體字，也不要使用韩文（括号里的韩文原名除外）。",
        "disclaimer": "AI 指引仅供参考，并非诊断。",
        "translated_notice": "本回答由韩文医院资料机器翻译而成。如需准确信息，请联系{center}。",
        "emergency": "如遇紧急情况，请立即拨打119或前往急诊室。",
        "errors": {
            "EMPTY_MESSAGE": "请输入问题。",
            "MESSAGE_TOO_LONG": "问题过长，请控制在{limit}个字符以内。",
            "UNSUPPORTED_LANGUAGE": "暂不支持该语言。",
            "SERVICE_UNAVAILABLE": "抱歉，服务暂时不可用，请稍后再试。",
            "RATE_LIMITED": "请求过于频繁，请稍后再试。",
            "AUDIO_TOO_LARGE": "录音过长，请控制在{seconds}秒以内。",
            "AUDIO_EMPTY": "未识别到语音，请重试。",
        },
    },
    # 품질 검증 전 (config.SUPPORTED_LANGS 기본값에 없음). 문구 검수 필요.
    "mn": {
        "name": "Mongolian (Монгол, Cyrillic script)",
        "hospital_name": "Catholic Kwandong University International St. Mary's Hospital",   # 몽골어 명칭 미정
        "reply_rule": "Answer in Mongolian (Cyrillic script) only. Зөвхөн монгол хэлээр хариулна уу.",
        "disclaimer": "AI-ийн мэдээлэл нь зөвхөн лавлагаа бөгөөд онош биш юм.",
        "translated_notice": "Энэ хариултыг солонгос хэлнээс машинаар орчуулсан. "
                             "Нарийвчилсан мэдээллийг {center}-с лавлана уу.",
        "emergency": "Яаралтай тохиолдолд 119 руу залгах эсвэл яаралтай тусламжийн тасагт хандана уу.",
        "errors": {
            "EMPTY_MESSAGE": "Асуултаа оруулна уу.",
            "MESSAGE_TOO_LONG": "Асуулт хэт урт байна. {limit} тэмдэгтээс бага байлгана уу.",
            "UNSUPPORTED_LANGUAGE": "Энэ хэлийг одоогоор дэмжихгүй байна.",
            "SERVICE_UNAVAILABLE": "Уучлаарай, үйлчилгээ түр ажиллахгүй байна.",
            "RATE_LIMITED": "Хүсэлт хэт олон байна. Түр хүлээнэ үү.",
            "AUDIO_TOO_LARGE": "Бичлэг хэт урт байна. {seconds} секундээс бага байлгана уу.",
            "AUDIO_EMPTY": "Яриа танигдсангүй. Дахин оролдоно уу.",
        },
    },
}

# =============================================================================
# ② 응급 키워드 — 질문 원문·한국어 번역문에서 찾고, 보이면 답변 위에 응급 안내를 먼저 표시
# =============================================================================
EMERGENCY_KEYWORDS = [
    # ko (번역문 검사용)
    "가슴 통증", "흉통", "숨을 못", "호흡곤란", "호흡 곤란", "의식", "마비", "심한 출혈", "피를 많이", "경련", "자살",
    # en
    "chest pain", "can't breathe", "cannot breathe", "short of breath", "unconscious", "fainted",
    "heavy bleeding", "seizure", "stroke", "suicide",
    # zh
    "胸痛", "呼吸困难", "喘不过气", "昏迷", "晕倒", "大出血", "抽搐", "中风", "自杀",
]

# 한국어 응급 표현 — 팀 화면 frontend/src/shared/chat/intentRouter.ts의 EMERGENCY와 같은 규칙 (화면·백엔드 판단 일치)
#   바꿀 때는 두 곳을 함께 고칠 것
EMERGENCY_PATTERNS_KO = [
    r"가슴\s*(이|가)?\s*(아파|아프|통증|답답|조여)",
    r"흉통",
    r"숨\s*(이|을)?\s*(차|막혀|못\s*쉬|쉬기\s*힘들|가빠)",
    r"호흡\s*곤란",
    r"의식\s*(이|을)?\s*(없|잃|흐려)",
    r"기절|실신",
    r"피\s*를?\s*토|토혈|각혈",
    r"마비|경련|발작",
    r"피\s*가?\s*(멈추지|안\s*멈)|심한\s*출혈",
]

# =============================================================================
# ③ LLM 프롬프트 (모델: Qwen3.6 35B, thinking 끔)
# =============================================================================

# -----------------------------------------------------------------------------
# EXPAND_V1 — 외국어 질문 → 한국어 번역 + 검색 키워드 (D안)
#   호출: translate.translate_and_expand()   temperature 0, max_tokens 200
#   입력: user = 사용자 질문 원문
#   출력: "KO: ..." / "KW: ..." 두 줄
#   검증: 2026-10-01 증상 25건 × en/zh, 상위 5개에 기대 진료과 100% (tests/check_symptom_hit.py)
# -----------------------------------------------------------------------------
EXPAND_V1 = """\
You prepare search queries for a Korean hospital information search engine.
The documents are written in Korean using hospital terminology
(e.g. 수부외과 for hand/wrist, 슬관절 for knee, 견관절 for shoulder, 족부 for foot/ankle).

For the user's question, output exactly two lines:
KO: <the question translated into natural Korean (if already Korean, copy it)>
KW: <5-8 Korean search keywords: relevant hospital department names as used in Korean hospitals,
     medical terms for the body part or symptom, separated by spaces>

Do not diagnose. Output only the two lines."""


def expand_messages(question: str) -> list[dict]:
    return [{"role": "system", "content": EXPAND_V1},
            {"role": "user", "content": question}]


# -----------------------------------------------------------------------------
# ANSWER_V3 — 한국어 참고 자료로 사용자 언어 답변 생성
#   호출: translate.answer()   temperature 0.3, max_tokens config.LLM_ANSWER_MAX_TOKENS
#   입력: system = 규칙 (대상 언어·병원 고정 명칭·국제진료센터 연락처 채움)
#         user   = [References] 한국어 자료 → [Question] 원문 질문 → 맨 끝에 reply_rule (그 언어로 다시)
#   V1→V2 (2026-10-06): 중국어 질문에 한국어로 답한 사례(停车费是多少？) 대응
#         - user 맨 끝을 한국어 질문 대신 '답변 언어 지시'로 끝냄 (모델은 마지막 지시를 잘 따름)
#         - [Question in Korean] 줄 제거 (한국어가 마지막에 와서 답변 언어를 끌어당김)
#   V2→V3 (2026-10-06): 병원 이름 번역이 실행마다 달라짐(国际圣玛丽医院/国际圣母医院)
#         - LANGS[lang]["hospital_name"]으로 고정 명칭 지정 (중국어: 国际圣母医院)
#   V3→V4 (2026-10-06): ① 중국어 답변이 가끔 번체자 → reply_rule에 간체자만 명시
#         ② 지명·역 이름에 한글이 그대로 섞임(检암站, 서해구청역) → 지명도 "번역 (한국어 원문)" 형식 규칙
#         (두 경우 모두 translate.answer()의 검사로 걸리면 REWRITE 1회)
#   V4→V5 (2026-10-06): 맞는 전문의 조각이 있는데도 다른 부위 전문의를 추천(손목 → 어깨·발목 교수)
#         → "증상 부위·내용과 전문분야가 맞는 의료진만, 없으면 이름 없이 진료과만" 규칙
#   V5 보완 (2026-10-11): 의료진을 5명까지 나열 → "최대 2명", 중국어 답변의 1./2./3. 번호 목록 → 문장으로
# -----------------------------------------------------------------------------
ANSWER_V5 = """\
You are the information chatbot of Catholic Kwandong University International St. Mary's Hospital (Korea).
The [References] are written in Korean. Use ONLY the [References], but write your whole answer in {lang_name}.
Be short and polite. Do not use numbered lists, bullet points or markdown; write 2-4 short paragraphs.

Rules:
- When you mention this hospital, always call it exactly "{hospital_name}". Do not translate its name any other way.
- Never invent doctors, departments, prices, hours, phone numbers or procedures that are not in the references.
- If the references cannot answer, say you cannot confirm it and suggest contacting the {center}. Nothing else.
- Do not mention disease names, causes, diagnostic criteria, treatments or drug names. You are not a doctor.
- Write every Korean proper noun as "<{lang_name} rendering> (<original Korean>)" so the patient can find it
  in Korea: departments ("Orthopedics (정형외과)"), doctors ("Prof. Kim Sang-hee (김상희 교수)"),
  and also place names, subway stations, bus stops and buildings ("Geomam Station (검암역)").
  Never leave a Korean word or a partly translated name outside parentheses.

If the user describes symptoms, answer only in this order:
1. Related department(s) from the references
2. Recommended doctor(s) and their specialty from the references.
   Recommend a doctor ONLY if their listed specialty matches the body part or symptom the user described
   (e.g. wrist/hand pain -> a specialist in 수부외과 (hand surgery); do NOT recommend a shoulder, knee or ankle
   specialist for wrist pain). Read every doctor in the references before choosing.
   Name at most 2 doctors. If no doctor's specialty matches, omit this item and do not name any doctor.
3. Last sentence: recommend visiting the hospital for an accurate diagnosis by a specialist.

For other questions (parking, check-ups, costs, location, certificates, etc.), summarize the references
in 3-5 sentences and add that amounts or hours may change, so the patient should confirm with the hospital.

{reply_rule}"""


def answer_messages(lang: str, question: str, context: str, center: str) -> list[dict]:
    L = LANGS[lang]
    system = ANSWER_V5.format(lang_name=L["name"], hospital_name=L["hospital_name"], center=center,
                              reply_rule=L["reply_rule"])
    user = f"[References]\n{context}\n\n[Question]\n{question}\n\n{L['reply_rule']}"
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]


# -----------------------------------------------------------------------------
# REWRITE_LANG_V2 — 답변 언어·표기가 어긋났을 때 다시 쓰기 (안전장치, 1회만)
#   호출: translate.answer() — 답변 언어가 다르거나, 중국어인데 번체자, 또는 괄호 밖에 한글이 남았을 때
#   temperature 0, max_tokens config.LLM_ANSWER_MAX_TOKENS
#   입력: user = 처음 답변 전문   출력: 고친 답변만
#   V1→V2 (2026-10-06): 번체자·괄호 밖 한글도 고치도록 지시 추가
# -----------------------------------------------------------------------------
REWRITE_LANG_V2 = """\
Rewrite the following hospital information answer in {lang_name}.
Keep every fact, number, department and doctor exactly the same. Do not add or remove information.
Write every Korean proper noun (departments, doctors, place names, stations, buildings) as
"<{lang_name} rendering> (<original Korean>)", e.g. "Orthopedics (정형외과)", "Geomam Station (검암역)".
No Korean words may remain outside parentheses.
Always call the hospital exactly "{hospital_name}".
Output only the rewritten answer.

{reply_rule}"""


def rewrite_messages(lang: str, answer_text: str) -> list[dict]:
    L = LANGS[lang]
    system = REWRITE_LANG_V2.format(lang_name=L["name"], hospital_name=L["hospital_name"],
                                    reply_rule=L["reply_rule"])
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"{answer_text}\n\n{L['reply_rule']}"}]


# =============================================================================
# ④ 한국어 (/v1/chat, 모델: 카카오 카나나 2 3B, 8k)
#   외국어 LANGS와 따로 둔다 (voice/config의 언어 목록·외국어 검사에 섞이지 않게)
# =============================================================================
KO: dict = {
    "disclaimer": "AI 안내는 참고용이며 진단이 아닙니다.",
    "emergency": "응급 상황일 수 있어요. 지금 바로 119에 전화하거나 가까운 응급실로 가세요.",
    "errors": {
        "EMPTY_MESSAGE": "질문을 입력해 주세요.",
        "MESSAGE_TOO_LONG": "질문이 너무 깁니다. {limit}자 이내로 입력해 주세요.",
        "UNSUPPORTED_LANGUAGE": "아직 지원하지 않는 언어입니다.",
        "SERVICE_UNAVAILABLE": "죄송합니다. 잠시 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        "RATE_LIMITED": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
        "AUDIO_TOO_LARGE": "녹음이 너무 깁니다. {seconds}초 이내로 말씀해 주세요.",
        "AUDIO_EMPTY": "음성이 인식되지 않았습니다. 다시 말씀해 주세요.",
    },
}

# -----------------------------------------------------------------------------
# 한국어 질문 종류 — LLM 없이 정규식으로 증상/일반을 나누고, 종류별 전용 프롬프트를 쓴다
#   2026-10-11: 카나나 3B가 한 프롬프트 안의 "증상용/일반용" 규칙을 구분하지 못해
#   "소화기내과 진료 시간표 알려줘"에도 증상 답변 틀로 답함 → 코드에서 먼저 나눔
# -----------------------------------------------------------------------------
SYMPTOM_PATTERNS_KO = [
    r"아파|아프|아픈|아팠|통증|쑤시|지끈|욱신|찌릿|저릿|따끔|화끈|콕콕|묵직|저려|저리|저림|결려|결리|뻐근|시려|시리|따가|쓰려|쓰리|쓰림",
    r"붓|부었|부어|가려|가렵|간지|두드러기|발진|물집|멍이|혹이|덩어리|만져져",
    r"기침|가래|콧물|코막|재채기|목이\s*(아|따|칼칼|부)|숨이|숨쉬|숨을|호흡",
    r"열이|열나|오한|몸살|어지러|어지럽|두통|복통|설사|변비|구토|메스꺼|울렁|토할|체했|소화가?\s*안",
    r"피가|출혈|혈변|혈뇨|소변.{0,4}(자주|안\s*나|아프|피)|저혈|빈혈|떨려|떨림|마비|경련",
    r"잠을?\s*못|불면|우울|불안|공황|기억력|증상|이상해|불편해",
]


def question_kind_ko(text: str) -> str:
    """"symptom" | "general" — 증상 표현이 있으면 증상 질문."""
    import re
    return "symptom" if any(re.search(p, text) for p in SYMPTOM_PATTERNS_KO) else "general"


# -----------------------------------------------------------------------------
# ANSWER_KO_SYMPTOM_V3 / ANSWER_KO_GENERAL_V3 — 한국어 답변 (카나나 3B), 질문 종류별 전용
#   V1 (10-11) POC 프롬프트 + 부위 일치 규칙 → V2 (10-11) 항목 이름 대신 답변 모양(OO)
#   → V3 (10-11) 증상/일반 분리, 의료진 최대 2명, 자료에 없는 일정·시간표는 대표전화 안내
#   남는 지시문 줄은 translate.clean_korean()이 지운다.
#   호출: translate.answer_korean()   temperature 0.3, max_tokens config.KO_LLM_ANSWER_MAX_TOKENS
# -----------------------------------------------------------------------------
_KO_COMMON = """\
당신은 가톨릭관동대학교 국제성모병원 홈페이지의 안내 챗봇입니다.
[참고 자료]에 있는 내용만 사용해서 한국어로 짧고 정중하게 답하세요.
참고 자료에 없는 의료진, 진료과, 비용, 시간, 전화번호, 절차는 지어내지 마세요.
병명, 원인, 진단 기준, 치료법, 약 이름은 말하지 마세요."""

ANSWER_KO_SYMPTOM_V3 = _KO_COMMON + """

아래 모양으로만 답하세요.
관련 진료과는 OO과입니다.
추천 의료진은 OOO 교수(전문분야: OO)입니다.
정확한 진단은 병원에 방문하여 전문의 진료를 받으시기 바랍니다.

추천 의료진은 최대 2명입니다. 전문분야가 질문한 부위·증상과 직접 맞는 교수만 쓰고,
맞는 교수가 없으면 그 줄을 빼세요. (손목 통증이면 수부외과 전문 교수만. 어깨·무릎·발목 전문 교수는 쓰지 않습니다.)"""

ANSWER_KO_GENERAL_V3 = _KO_COMMON + """

질문에 대한 내용을 참고 자료에서 찾아 2~5문장으로 안내하세요.
진료 일정, 진료 시간표, 예약 가능한 시간처럼 참고 자료에 없는 내용이면
"해당 내용은 확인이 어렵습니다. 대표전화 {phone} 또는 홈페이지 온라인 예약으로 문의해 주세요."라고만 답하세요.
금액이나 시간을 안내했다면 마지막에 "금액이나 시간은 변동될 수 있으니 병원에 확인해 주세요."를 붙이세요."""


def answer_ko_messages(question: str, context: str, kind: str, phone: str) -> list[dict]:
    system = ANSWER_KO_SYMPTOM_V3 if kind == "symptom" else ANSWER_KO_GENERAL_V3.format(phone=phone)
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"[참고 자료]\n{context}\n\n[질문]\n{question}"}]
