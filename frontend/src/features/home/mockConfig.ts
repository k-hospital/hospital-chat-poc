import type { ChatConfig } from './types';

// 백엔드 연결 전 화면 확인용 목업
export const mockConfig: ChatConfig = {
  hospitalName: 'OO병원',
  isOperatingHours: true,
  operatingHoursText: '평일 08:30 – 17:30',
  hero: {
    eyebrow: '가장 많이 찾는 메뉴',
    title: '진료 예약',
    description: '진료과 · 의료진 · 시간을 고르면\n바로 예약돼요',
    ctaLabel: '예약하기',
    intent: 'booking.start',
  },
  tiles: [
    { id: 'outpatient', label: '외래 안내', description: '접수 · 진료 절차', icon: 'clipboard', intent: 'info.outpatient', requiresAuth: false, order: 1, visible: true },
    { id: 'doctors', label: '의료진 찾기', description: '진료과 · 전문 분야', icon: 'stethoscope', intent: 'doctor.search', requiresAuth: false, order: 2, visible: true },
    { id: 'directions', label: '오시는 길', description: '교통 · 주차', icon: 'pin', intent: 'info.directions', requiresAuth: false, order: 3, visible: true },
    { id: 'health', label: '건강 정보', description: '질환 · 검사 안내', icon: 'book', intent: 'info.health', requiresAuth: false, order: 4, visible: true },
  ],
  faqs: [
    { id: 'parking', label: '주차 안내', icon: 'pin', intent: 'faq.parking', requiresAuth: false, order: 1, visible: true },
    { id: 'hours', label: '진료 시간', icon: 'clipboard', intent: 'faq.hours', requiresAuth: false, order: 2, visible: true },
    { id: 'certificate', label: '증명서 발급', icon: 'clipboard', intent: 'faq.certificate', requiresAuth: false, order: 3, visible: true },
    { id: 'booking-lookup', label: '예약 조회', icon: 'search', intent: 'booking.lookup', requiresAuth: true, order: 4, visible: true },
  ],
  disclaimer: 'AI 안내는 참고용이며 진단이 아닙니다',
};
