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

  // 부사·조사·어순이 달라도 응급을 놓치지 않아야 한다 (LLM 평가에서 규칙이 놓친 표현 포함)
  it.each([
    '가슴이 너무 아파요', '가슴이 갑자기 꽉 조여요', '가슴을 쥐어짜는 것 같고 식은땀이 나요', '심장이 아파요',
    '숨이 너무 차요', '숨을 못 쉬겠어요', '숨쉬기가 너무 힘들어요', '숨이 안 쉬어져요',
    '사람이 쓰러졌어요', '갑자기 쓰러질 것 같아요', '옆 사람이 의식이 없어요', '정신을 잃었어요',
    '피가 계속 나는데 멈추질 않아요', '피가 많이 나요', '피를 왈칵 쏟았어요',
    '갑자기 한쪽 팔다리에 힘이 안 들어와요', '갑자기 눈이 안 보여요', '말이 어눌해졌어요', '입이 한쪽으로 돌아갔어요',
    '아이가 거품을 물고 경련해요',
  ])('표현이 달라도 응급으로 판별: %s', (text) => {
    expect(routeQuestion(text)).toEqual({ kind: 'emergency' });
  });

  // 의료진 검수 전 임시로 응급 처리하는 항목 (놓치는 것보다 한 번 더 안내하는 편이 안전)
  it.each(['죽고 싶어요', '농약을 마셨어요', '약을 과다 복용했어요', '임신 중인데 피가 나요', '아나필락시스가 온 것 같아요'])(
    '검수 전 임시 응급: %s', (text) => {
      expect(routeQuestion(text)).toEqual({ kind: 'emergency' });
    },
  );

  // 응급 단어와 겹치는 일상 표현은 응급으로 보지 않는다 (불필요한 119 안내 방지)
  it.each([
    '숨은 맛집 차 한잔 하고 싶어요', '숨 돌릴 틈이 없어요', '정신이 없어요 바빠서', '다리에 힘이 없어요',
    '갑자기 어깨가 결려요', '피검사 결과 알려주세요', '배송 문의드려요', '허리가 아파요', '목이 아파요',
    '주차 되나요',
  ])('응급이 아닌 문장: %s', (text) => {
    expect(routeQuestion(text).kind).not.toBe('emergency');
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

  it.each(['병원 어떻게 가요?', '병원 가는 방법', '거기 가려면 어떻게 해', '길 좀 알려줘', '응급실 위치 알려줘'])(
    '오시는 길 일상 표현: %s', (text) => {
      expect(intentOf(text)).toBe('info.directions');
    },
  );

  it('교통수단을 말하면 오시는 길의 해당 탭 주제로 판별', () => {
    expect(routeQuestion('지하철로 가는 방법')).toMatchObject({ intent: 'info.directions', topic: 'subway' });
    expect(routeQuestion('버스 노선 알려주세요')).toMatchObject({ intent: 'info.directions', topic: 'bus' });
    expect(routeQuestion('자가용으로 가는 방법')).toMatchObject({ intent: 'info.directions', topic: 'car' });
  });

  it("'주차'는 교통수단(차)보다 주차 안내가 우선", () => {
    expect(intentOf('주차 요금은요?')).toBe('faq.parking');
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
