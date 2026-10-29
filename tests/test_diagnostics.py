from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from blogpost.publishers.diagnostics import save_diagnostic


class DiagnosticHtmlTests(unittest.TestCase):
    def test_credentials_are_removed_without_losing_category_structure(self):
        csrf = "csrf-" + "A" * 90
        password = "password with spaces " + "B" * 70
        secret = "secret with spaces " + "C" * 70
        html = f'''<!-- diagnostic {{"url":"https://example.test/?token={csrf}"}} -->
<html><head><meta name="csrf-token" content="{csrf}">
<script>window.config={{"secret":"{secret}"}};</script></head>
<body onload="fetch('https://example.test')">
<input id="password" type="password" value="{password}">
<input type="hidden" name="_csrf" value="{csrf}">
<input id="selfType" readonly value="AI"><ul id="selfType_list"><li>AI</li></ul>
<div data-token="{csrf}" style="background:url(https://example.test)">个人分类</div>
<a href="https://example.test/?token={csrf}">分类管理</a>
<textarea>Authorization: Bearer {csrf}
Cookie: session={csrf}; preference=private
{{"password":"{password}","secret":"{secret}"}}</textarea>
</body></html>'''
        with tempfile.TemporaryDirectory() as root:
            saved = save_diagnostic(Path(root), html).read_text(encoding="utf-8")

        for value in (csrf, password, secret, "A" * 30, "B" * 30, "C" * 30):
            self.assertFalse(value in saved, "credential or suffix leaked into diagnostic")
        self.assertNotIn("<script", saved)
        self.assertNotIn("onload=", saved)
        self.assertNotIn("https://example.test", saved)
        self.assertIn('id="selfType"', saved)
        self.assertIn('id="selfType_list"', saved)
        self.assertIn("个人分类", saved)
        self.assertIn("AI", saved)

    def test_html_entities_and_long_quoted_values_do_not_leave_secret_suffixes(self):
        secret = "long secret with spaces " + "S" * 100
        html = f'''<meta content='{secret}' name='csrf-token'>
<input value='{secret}' name='access_token'>
<pre>{{&quot;api_key&quot;:&quot;{secret}&quot;}}
refresh_token='{secret}'</pre>'''
        with tempfile.TemporaryDirectory() as root:
            saved = save_diagnostic(Path(root), html).read_text(encoding="utf-8")

        self.assertNotIn(secret, saved)
        self.assertNotIn("S" * 30, saved)

    def test_output_is_inert_and_size_limited(self):
        html = '<iframe src="https://example.test">private</iframe><svg><script>private</script></svg>'
        html += '<form action="https://example.test"><button onclick="alert(1)">确认</button></form>'
        html += '<p>' + 'x' * 600000 + '</p>'
        with tempfile.TemporaryDirectory() as root:
            saved = save_diagnostic(Path(root), html).read_text(encoding="utf-8")

        self.assertLessEqual(len(saved), 500000)
        for value in ("iframe", "<svg", "<script", "onclick", "action=", "https://example.test"):
            self.assertFalse(value in saved, f"active content remains: {value}")
        HTMLParser().feed(saved)


if __name__ == "__main__":
    unittest.main()
