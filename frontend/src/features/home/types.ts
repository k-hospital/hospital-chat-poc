// /v1/config 응답 타입 — 백엔드 Pydantic 스키마(app/schemas/config.py)와 1:1 대응
export type IconName = 'calendar' | 'clipboard' | 'stethoscope' | 'pin' | 'book' | 'search';

export interface MenuItem {
  id: string;
  label: string;
  description?: string;
  icon: IconName;
  intent: string;          // 탭 시 POST /v1/chat/messages {type:"action", intent}
  requiresAuth: boolean;   // true면 자물쇠 표시 → 인증 플로우
  order: number;
  visible: boolean;
}

export interface HeroConfig {
  eyebrow: string;
  title: string;
  description: string;
  ctaLabel: string;
  intent: string;
}

export interface ChatConfig {
  hospitalName: string;
  isOperatingHours: boolean;   // 서버 시간 기준 판단 결과
  operatingHoursText: string;  // 예: "평일 08:30 – 17:30"
  hero: HeroConfig;
  tiles: MenuItem[];           // 4개 타일
  faqs: MenuItem[];            // 자주 찾는 질문 칩
  disclaimer: string;          // 비어 있으면 기본 문구 강제
}

export interface MainScreenHandlers {
  onAction: (item: { intent: string; label: string; requiresAuth: boolean }) => void;
  onSendText: (text: string) => void;
  onAgent: () => void;     // 주간: 상담원 연결
  onCallback: () => void;  // 야간: 콜백 요청
  onSettings: () => void;  // 기능별 연결 주소 설정 화면
}
