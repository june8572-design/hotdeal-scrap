import os
import tempfile
import unittest
from pathlib import Path

import enrich_hotdeal_details as e


class NaverBrandConnectorLinkTests(unittest.TestCase):
    def test_extract_links_deduplicates_and_normalizes(self):
        html = '''
        <a href="https://example.com/a">A</a>
        <a href="/relative/path">B</a>
        <a href="https://example.com/a">C</a>
        '''
        links = e.extract_links(html)
        self.assertEqual(links, ["https://example.com/a", "https://hotdeal.zip/relative/path"])

    def test_build_brand_connector_link_uses_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "NAVER_BRAND_CONNECTOR_URL_TEMPLATE=https://brand.example/redirect?u={url}&deal={deal_id}",
                encoding="utf-8",
            )

            old_env_path = e.ENV_PATH
            old_var = os.environ.pop("NAVER_BRAND_CONNECTOR_URL_TEMPLATE", None)
            try:
                e.ENV_PATH = env_path
                built = e.build_brand_connector_link("https://shop.example/item?a=1&b=2", deal_id=123)
                self.assertEqual(
                    built,
                    "https://brand.example/redirect?u=https%3A%2F%2Fshop.example%2Fitem%3Fa%3D1%26b%3D2&deal=123",
                )
            finally:
                e.ENV_PATH = old_env_path
                if old_var is not None:
                    os.environ["NAVER_BRAND_CONNECTOR_URL_TEMPLATE"] = old_var
                else:
                    os.environ.pop("NAVER_BRAND_CONNECTOR_URL_TEMPLATE", None)

    def test_build_brand_connector_link_returns_none_without_template(self):
        old_var = os.environ.pop("NAVER_BRAND_CONNECTOR_URL_TEMPLATE", None)
        try:
            built = e.build_brand_connector_link("https://shop.example/item")
            self.assertIsNone(built)
        finally:
            if old_var is not None:
                os.environ["NAVER_BRAND_CONNECTOR_URL_TEMPLATE"] = old_var


if __name__ == "__main__":
    unittest.main()
