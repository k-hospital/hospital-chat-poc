from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from app.features.config.schemas import ChatConfig, HeroConfig, MenuItem

router = APIRouter(prefix="/v1", tags=["config"])

KST = ZoneInfo("Asia/Seoul")
OPEN, CLOSE = time(8, 30), time(17, 30)
HOLIDAYS: set[str] = set()  # TODO: 관리자 콘솔/DB의 휴일 캘린더에서 로드 ("2026-10-03" 형식)
DEFAULT_DISCLAIMER = "AI 안내는 참고용이며 진단이 아닙니다"


def is_operating_hours(now: datetime | None = None) -> bool:
    """사용자 기기 시간이 아닌 서버(KST) 기준으로 판단."""
    now = now or datetime.now(KST)
    if now.weekday() >= 5 or now.strftime("%Y-%m-%d") in HOLIDAYS:
        return False
    return OPEN <= now.time() < CLOSE


@router.get("/config", response_model=ChatConfig, response_model_by_alias=True)
async def get_config() -> ChatConfig:
    # TODO: 메뉴/문구는 관리자 콘솔이 저장한 DB 값으로 교체
    disclaimer = ""  # DB 값
    return ChatConfig(
        hospital_name="OO병원",
        is_operating_hours=is_operating_hours(),
        operating_hours_text="평일 08:30 – 17:30",
        hero=HeroConfig(
            eyebrow="가장 많이 찾는 메뉴", title="진료 예약",
            description="진료과 · 의료진 · 시간을 고르면\n바로 예약돼요",
            cta_label="예약하기", intent="booking.start",
        ),
        tiles=[
            MenuItem(id="outpatient", label="외래 안내", description="접수 · 진료 절차", icon="clipboard", intent="info.outpatient", order=1),
            MenuItem(id="doctors", label="의료진 찾기", description="진료과 · 전문 분야", icon="stethoscope", intent="doctor.search", order=2),
            MenuItem(id="directions", label="오시는 길", description="교통 · 주차", icon="pin", intent="info.directions", order=3),
            MenuItem(id="health", label="건강 정보", description="질환 · 검사 안내", icon="book", intent="info.health", order=4),
        ],
        faqs=[
            MenuItem(id="parking", label="주차 안내", icon="pin", intent="faq.parking", order=1),
            MenuItem(id="hours", label="진료 시간", icon="clipboard", intent="faq.hours", order=2),
            MenuItem(id="certificate", label="증명서 발급", icon="clipboard", intent="faq.certificate", order=3),
            MenuItem(id="booking-lookup", label="예약 조회", icon="search", intent="booking.lookup", requires_auth=True, order=4),
        ],
        # 면책 문구는 삭제 불가: 비어 있으면 기본 문구
        disclaimer=disclaimer.strip() or DEFAULT_DISCLAIMER,
    )
