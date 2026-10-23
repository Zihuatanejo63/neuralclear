import json
from html.parser import HTMLParser
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for key in ("href", "src"):
            if key in attrs:
                self.links.append(attrs[key])


class WebsiteTests(unittest.TestCase):
    def test_machine_files_are_real_non_html(self):
        for name in ("robots.txt", "llms.txt", "sitemap.xml", ".well-known/agent-skills"):
            text = (ROOT / name).read_text()
            self.assertNotIn("<html", text.lower())
        self.assertEqual(json.loads((ROOT / ".well-known/agent-skills").read_text())["status"],
                         "prototype")
        ET.parse(ROOT / "sitemap.xml")
        self.assertTrue((ROOT / "404.html").is_file())
        self.assertIn("application/json", (ROOT / "_headers").read_text())

    def test_local_links_and_anchors_exist(self):
        parser = Links()
        parser.feed((ROOT / "index.html").read_text())
        for link in parser.links:
            if link.startswith("#"):
                self.assertIn(link[1:], parser.ids)
            elif link.startswith("./"):
                self.assertTrue((ROOT / link).is_file(), link)

    def test_no_stale_metrics_or_live_claims(self):
        content = (ROOT / "index.html").read_text() + (ROOT / "site.js").read_text()
        for stale in ("127/127", "LIVE OUTPUT", "No frozen money, ever", "/Users/"):
            self.assertNotIn(stale, content)
        self.assertIn("2026-10-29", content)
        self.assertIn("54bd57f", content)
