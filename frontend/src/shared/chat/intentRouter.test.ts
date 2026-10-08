import { describe, expect, it } from 'vitest';
import { routeQuestion, SYMPTOM_INTENT } from './intentRouter';

const intentOf = (text: string) => {
  const r = routeQuestion(text);
  return r.kind === 'intent' ? r.intent : r.kind;
};

describe('routeQuestion', () => {
  it('배 아파 → 증상별 진료 안내 (소화기)', () => {
    expect(routeQuestion('배 아파')).toMatchObject({ kind: 'intent', intent: SYMPTOM_INTENT, topic: 'digestive' });
  });

  it.each(['배가 너무 아파요', '배아파', '속이 쓰려요', '어제부터 설사해요', '체한 것 같아요'])(
    '소화기 증상 표현: %s', (text) => {
      expect(routeQuestion(text)).toMatchObject({ intent: SYMPTOM_INTENT, topic: 'digestive' });
    },
  );

  it('두통·호흡기 증상은 각자 주제로 구분', () => {
    expect(routeQuestion('머리가 아파요')).toMatchObject({ topic: 'headache' });
    expect(routeQuestion('기침이 계속 나요')).toMatchObject({ topic: 'respiratory' });
  });

  it.each(['가슴이 아파요', '숨이 차요', '피를 토했어요', '갑자기 기절했어요'])(
    '응급 신호는 이동하지 않고 응급으로 판별: %s', (text) => {
      expect(routeQuestion(text)).toEqual({ kind: 'emergency' });
    },
  );

  it('응급 신호가 다른 증상과 함께 있어도 응급이 우선', () => {
    expect(routeQuestion('배가 아프고 숨이 차요')).toEqual({ kind: 'emergency' });
  });

  it('예약 조회는 진료 예약보다 먼저 판별', () => {
    expect(intentOf('예약 확인하고 싶어요')).toBe('booking.lookup');
    expect(intentOf('예약하고 싶어요')).toBe('booking.start');
  });

  it.each([
    ['주차 되나요?', 'faq.parking'],
    ['병원 위치가 어디야', 'info.directions'],
    ['진료 시간 알려줘', 'faq.hours'],
    ['진단서 발급', 'faq.certificate'],
    ['소화기내과 교수님 찾아요', 'doctor.search'],
  ])('안내 질문: %s → %s', (text, intent) => {
    expect(intentOf(text)).toBe(intent);
  });

  it("'배'가 들어가도 증상이 아닌 말은 증상으로 보지 않음", () => {
    expect(intentOf('배송 문의')).toBe('unknown');
    expect(intentOf('배우고 싶어요')).toBe('unknown');
  });

  it('맞는 규칙이 없거나 빈 입력이면 unknown', () => {
    expect(routeQuestion('안녕하세요')).toEqual({ kind: 'unknown' });
    expect(routeQuestion('   ')).toEqual({ kind: 'unknown' });
  });
});
