import sqlite3
import unittest

import todayhumor_dryrun as th


class TodayHumorStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.cur = self.conn.cursor()

    def tearDown(self) -> None:
        self.conn.close()

    def test_ensure_storage_schema_creates_todayhumor_posts_table(self):
        th.ensure_storage_schema(self.cur)

        self.cur.execute("PRAGMA table_info(todayhumor_posts)")
        columns = {row[1] for row in self.cur.fetchall()}

        self.assertIn("url", columns)
        self.assertIn("category", columns)
        self.assertIn("score", columns)
        self.assertIn("raw_json", columns)

    def test_save_posts_upserts_by_url(self):
        th.ensure_storage_schema(self.cur)

        rows = [
            {
                "url": "https://m.todayhumor.co.kr/view.php?table=humordata&no=1",
                "no": 1,
                "date": "2026/03/30 12:00",
                "writer": "writer-a",
                "title": "첫 제목",
                "views": 10,
                "reco": 2,
                "comments": 3,
                "board_table": "humordata",
                "board_name": "유머자료",
                "category": "humor",
                "score": 12.5,
            }
        ]

        inserted = th.save_posts(self.cur, rows)
        self.assertEqual(inserted, 1)

        updated_rows = [dict(rows[0])]
        updated_rows[0]["title"] = "수정된 제목"
        updated_rows[0]["views"] = 99
        updated_rows[0]["score"] = 42.0

        inserted_again = th.save_posts(self.cur, updated_rows)
        self.assertEqual(inserted_again, 1)

        self.cur.execute(
            "SELECT title, views, score, board_table, category FROM todayhumor_posts WHERE url = ?",
            (rows[0]["url"],),
        )
        saved = self.cur.fetchone()

        self.assertEqual(saved["title"], "수정된 제목")
        self.assertEqual(saved["views"], 99)
        self.assertEqual(saved["score"], 42.0)
        self.assertEqual(saved["board_table"], "humordata")
        self.assertEqual(saved["category"], "humor")


if __name__ == "__main__":
    unittest.main()
