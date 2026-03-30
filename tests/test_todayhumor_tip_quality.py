import unittest

import todayhumor_dryrun as th


class TodayHumorTipQualityTests(unittest.TestCase):
    def test_is_tip_candidate_rejects_help_request_title(self):
        self.assertFalse(th.is_tip_candidate("안녕하세요 타이어 바꾸려는데 추천좀 [5]"))

    def test_is_tip_candidate_rejects_help_request_title_with_ask_phrase(self):
        self.assertFalse(th.is_tip_candidate("돈 받는 방법 좀 알려주세요"))

    def test_is_tip_candidate_rejects_question_ending_title(self):
        self.assertFalse(th.is_tip_candidate("이거 어떤 게 좋을까요?"))

    def test_is_tip_candidate_accepts_explicit_tip_title(self):
        self.assertTrue(th.is_tip_candidate("휴대폰 구매 비교 후 사기 안당하는 법 및 꿀팁"))

    def test_is_tip_candidate_can_use_content_text_signal(self):
        self.assertTrue(
            th.is_tip_candidate(
                "제목은 평범함",
                "아래에 초보자용 사용법과 절약 방법, 체크리스트를 정리했습니다.",
            )
        )

    def test_is_tip_candidate_rejects_short_question_even_with_recommend_keyword(self):
        self.assertFalse(th.is_tip_candidate("원두 추천 부탁드려요"))


if __name__ == "__main__":
    unittest.main()
