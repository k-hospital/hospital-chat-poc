import { describe, expect, it } from 'vitest';
import { buildSuggestions, parseOptionLists } from './suggestionsFromRows.mjs';

const LISTS = [
  ['화면', '내부 키', null, '연결 기능', '내부 키', null, '사용 여부'],
  ['메인', 'home', null, '오시는 길', 'info.directions', null, '사용'],
  ['오시는 길', 'info.directions', null, '주차 안내', 'faq.parking', null, '중지'],
  ['증상 안내', 'symptom.guide', null, '상담원 연결', 'action.agent', null, null],
  ["※ '내부 키' 열은 수정하지 마세요.", null, null, null, null, null, null],
];
const HEAD = ['질문', '화면', '연결 기능', '순서', '사용'];
const build = (...rows) => buildSuggestions([HEAD, ...rows], LISTS);

describe('parseOptionLists', () => {
  it('화면·연결 기능과 내부 키를 읽고 안내 문구 줄은 건너뜀', () => {
    const { screens, features, errors } = parseOptionLists(LISTS);
    expect(errors).toEqual([]);
    expect([...screens]).toEqual([['메인', 'home'], ['오시는 길', 'info.directions'], ['증상 안내', 'symptom.guide']]);
    expect(features.get('상담원 연결')).toBe('action.agent');
    expect(features.size).toBe(3);
  });

  it('내부 키가 비었거나 이름이 중복이면 오류', () => {
    const { errors } = parseOptionLists([['화면', '내부 키'], ['메인', ''], ['메인', 'home2'], ['메인', 'home3']]);
    expect(errors.join('\n')).toContain("내부 키가 비어 있습니다");
    expect(errors.join('\n')).toContain('중복');
  });
});

describe('buildSuggestions', () => {
  it('화면 키·기능 키로 변환하고, 순서대로 정렬하며, 중지한 줄은 뺌', () => {
    const { data, errors } = build(
      ['지하철로 가는 방법', '오시는 길', '오시는 길', 1, '사용'],
      ['상담원연결', '메인', '상담원 연결', 2, '사용'],
      ['병원 오시는길', '메인', '오시는 길', 1, '사용'],
      ['주차 되나요?', '메인', '주차 안내', 3, '중지'],
    );
    expect(errors).toEqual([]);
    expect(data).toEqual({
      screens: {
        home: [
          { text: '병원 오시는길', intent: 'info.directions', label: '오시는 길' },
          { text: '상담원연결', intent: 'action.agent', label: '상담원 연결' },
        ],
        'info.directions': [{ text: '지하철로 가는 방법', intent: 'info.directions', label: '오시는 길' }],
      },
    });
  });

  it('순서가 같으면 입력한 줄 순서를 따르고, 빈 줄은 무시', () => {
    const { data } = build(['가', '메인', '오시는 길', 1, '사용'], [null, null, null, null, null], ['나', '메인', '오시는 길', 1, '사용']);
    expect(data.screens.home.map((s) => s.text)).toEqual(['가', '나']);
  });

  it('엑셀이 숫자 칸을 문자열로 넘겨도 순서를 인식', () => {
    const { data, errors } = build(['가', '메인', '오시는 길', '2', '사용'], ['나', '메인', '오시는 길', '1', '사용']);
    expect(errors).toEqual([]);
    expect(data.screens.home.map((s) => s.text)).toEqual(['나', '가']);
  });

  it('목록에 없는 화면·기능, 잘못된 순서·사용 값은 줄 번호와 함께 오류', () => {
    const { data, errors } = build(
      ['가', '없는화면', '오시는 길', 1, '사용'],
      ['나', '메인', '없는기능', 1, '사용'],
      ['다', '메인', '오시는 길', 0, '사용'],
      ['라', '메인', '오시는 길', 1, '네'],
    );
    expect(data).toBeNull();
    const text = errors.join('\n');
    expect(text).toContain("'추천질문' 시트 2행: 화면 '없는화면'");
    expect(text).toContain("3행: 연결 기능 '없는기능'");
    expect(text).toContain('4행: 순서는 1 이상의 정수');
    expect(text).toContain("5행: 사용 칸은 '사용' 또는 '중지'");
  });

  it('질문·화면·기능이 비어 있으면 오류 (줄 일부만 채운 경우 포함)', () => {
    const { errors } = build([null, '메인', null, 1, '사용']);
    const text = errors.join('\n');
    expect(text).toContain('질문이 비어 있습니다');
    expect(text).toContain('연결 기능이 비어 있습니다');
  });

  it('같은 화면의 중복 질문(띄어쓰기만 다른 경우 포함)은 오류, 다른 화면이면 허용', () => {
    expect(build(['주차 되나요', '메인', '주차 안내', 1, '사용'], ['주차되나요', '메인', '주차 안내', 2, '사용']).errors.join('\n'))
      .toContain('같은 질문');
    expect(build(['주차 되나요', '메인', '주차 안내', 1, '사용'], ['주차 되나요', '오시는 길', '주차 안내', 1, '사용']).errors).toEqual([]);
  });

  it('머리글이 다르면 오류', () => {
    const { data, errors } = buildSuggestions([['질문', '장소', '연결 기능', '순서', '사용'], ['가', '메인', '오시는 길', 1, '사용']], LISTS);
    expect(data).toBeNull();
    expect(errors[0]).toContain('머리글');
  });

  it("'사용'인 줄이 하나도 없으면 오류", () => {
    const { data, errors } = build(['가', '메인', '오시는 길', 1, '중지']);
    expect(data).toBeNull();
    expect(errors[0]).toContain('하나도 없습니다');
  });
});
