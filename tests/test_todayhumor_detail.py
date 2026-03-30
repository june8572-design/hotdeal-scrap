import unittest

import todayhumor_dryrun as th


SAMPLE_HTML = """
<div class=\"view_title\"><span class=\"view_subject\">샘플 제목</span></div>
<div class=\"view_spec\">
  <span class=\"view_spec_each_span\">작성자 : <span class=\"view_writer_span\"><span id='viewPageWriterNameSpan'><a><b>샘플작성자</b></a></span></span><br />
  <span class=\"view_spec_each_span\">추천 : <span class=\"view_okNok\">7</span><br />
  <span class=\"view_spec_each_span\">조회수 : <span class=\"view_viewCount\">123회</span></span><br />
  <span class=\"view_spec_each_span\">댓글수 : <span class=\"view_replyCount\">4개</span></span><br />
  <span class=\"view_spec_each_span\">등록시간 : <span class=\"view_bestRegDate\">2026/03/30 10:02:07</span></span>
</div>
<div class=\"viewContent\" id=\"viewContent\">
  <div class='upfile' id='upfile1'>
    <img src='http://example.com/image1.jpg' width='100' height='200'>
  </div>
  첫 줄입니다.<br />둘째 줄입니다.&nbsp;공백 포함
</div>
<table class='view_page_source_div'>
<tr>
  <td class='source_title'>출처</td>
  <td class='source_content'>원문 링크<br />https://example.com/source</td>
</tr>
</table>
"""


class TodayHumorDetailTests(unittest.TestCase):
    def test_parse_detail_page_extracts_main_fields(self):
        parsed = th.parse_detail_page(SAMPLE_HTML)

        self.assertEqual(parsed["title"], "샘플 제목")
        self.assertEqual(parsed["writer"], "샘플작성자")
        self.assertEqual(parsed["reco"], 7)
        self.assertEqual(parsed["views"], 123)
        self.assertEqual(parsed["comments"], 4)
        self.assertEqual(parsed["date"], "2026/03/30 10:02:07")
        self.assertEqual(parsed["content_text"], "첫 줄입니다.\n둘째 줄입니다. 공백 포함")
        self.assertEqual(parsed["content_images_json"], ["http://example.com/image1.jpg"])
        self.assertIn("원문 링크", parsed["source_text"])
        self.assertIn("https://example.com/source", parsed["source_text"])


if __name__ == "__main__":
    unittest.main()
