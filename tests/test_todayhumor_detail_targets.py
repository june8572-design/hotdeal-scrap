import unittest

import todayhumor_dryrun as th


class TodayHumorDetailTargetTests(unittest.TestCase):
    def test_parse_detail_categories_returns_all_when_empty(self):
        categories = th.parse_detail_categories("")
        self.assertEqual(categories, {"good", "humor", "tip"})

    def test_parse_detail_categories_filters_requested_values(self):
        categories = th.parse_detail_categories("good, tip")
        self.assertEqual(categories, {"good", "tip"})

    def test_filter_items_for_detail_categories_keeps_matching_categories(self):
        items = [
            {"title": "좋은글", "category": "good"},
            {"title": "유머글", "category": "humor"},
            {"title": "꿀팁글", "category": "tip"},
        ]
        filtered = th.filter_items_for_detail_categories(items, {"tip", "good"})
        self.assertEqual([item["title"] for item in filtered], ["좋은글", "꿀팁글"])

    def test_parse_detail_categories_rejects_unknown_value(self):
        with self.assertRaises(ValueError):
            th.parse_detail_categories("good,unknown")


if __name__ == "__main__":
    unittest.main()
