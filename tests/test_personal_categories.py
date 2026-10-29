from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch

from blogpost.publishers.personal_categories import CategoryClient, CategoryError, ensure_personal_category


class CategorySite:
    def __init__(self, categories=(), fields=()):
        self.items = list(categories)
        self.fields = list(fields)
        self.writes = []
        self.refreshed = None
        self.queries = 0
        self.before_second_query = None
        self.save_error = False
        self.persist_save = True

    def categories(self):
        self.queries += 1
        if self.queries == 2 and self.before_second_query:
            self.before_second_query()
        return [dict(item) for item in self.items]

    def manager(self):
        return nullcontext(self)

    def form(self, categories):
        return list(self.fields)

    def save(self, fields):
        self.writes.append(fields)
        if self.persist_save:
            names = [value for key, value in fields if key.startswith("name[")]
            added = next(value for value in names if value not in [item["name"] for item in self.items])
            self.items.append(dict(id="99", name=added))
        if self.save_error:
            raise CategoryError("request timed out")
        return self.persist_save

    def refresh(self, categories):
        self.refreshed = categories


class PersonalCategoryCreationTests(unittest.TestCase):
    def test_existing_category_is_reused_without_saving(self):
        site = CategorySite([dict(id="7", name="AI")])
        ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [])
        self.assertEqual(site.refreshed, [dict(id="7", name="AI")])

    def test_empty_placeholder_is_filled_once(self):
        site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
        ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [[("sort[]", "1"), ("name[]", "AI")]])
        self.assertEqual(site.refreshed, [dict(id="99", name="AI")])

    def test_existing_ids_names_and_sort_are_preserved(self):
        fields = [("id[4]", "42"), ("sort[4]", "4"), ("name[4]", "工程 & 实践")]
        site = CategorySite([dict(id="42", name="工程 & 实践")], fields)
        ensure_personal_category(site, 'AI "工具"')
        self.assertEqual(site.writes, [fields + [("sort[5]", "5"), ("name[5]", 'AI "工具"')]])
        self.assertEqual(site.items[0], dict(id="42", name="工程 & 实践"))

    def test_concurrent_creation_is_reused(self):
        site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
        site.before_second_query = lambda: site.items.append(dict(id="8", name="AI"))
        ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [])
        self.assertEqual(site.refreshed, [dict(id="8", name="AI")])

    def test_unrelated_concurrent_change_stops_before_write(self):
        site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
        site.before_second_query = lambda: site.items.append(dict(id="8", name="其他"))
        with self.assertRaises(CategoryError):
            ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [])

    def test_timeout_rechecks_and_does_not_repeat_save(self):
        for persisted in (True, False):
            with self.subTest(persisted=persisted):
                site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
                site.save_error, site.persist_save = True, persisted
                if persisted:
                    ensure_personal_category(site, "AI")
                    self.assertIsNotNone(site.refreshed)
                else:
                    with self.assertRaises(CategoryError):
                        ensure_personal_category(site, "AI")
                    self.assertIsNone(site.refreshed)
                self.assertEqual(len(site.writes), 1)

    def test_unsuccessful_save_cannot_continue(self):
        site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
        site.persist_save = False
        with self.assertRaises(CategoryError):
            ensure_personal_category(site, "AI")
        self.assertEqual(len(site.writes), 1)
        self.assertIsNone(site.refreshed)

    def test_invalid_name_or_category_limit_never_writes(self):
        for name in ("", "  ", "x" * 51, "😀" * 26):
            with self.subTest(name_length=len(name)):
                site = CategorySite()
                with self.assertRaises(CategoryError):
                    ensure_personal_category(site, name)
                self.assertEqual(site.writes, [])
        site = CategorySite([dict(id=str(i), name=f"分类{i}") for i in range(50)])
        with self.assertRaises(CategoryError):
            ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [])

    def test_existing_category_is_reused_even_at_limit(self):
        site = CategorySite([dict(id=str(i), name=f"分类{i}") for i in range(50)])
        ensure_personal_category(site, "分类0")
        self.assertEqual(site.writes, [])
        self.assertEqual(len(site.refreshed), 50)

    def test_form_mismatch_and_index_collision_never_write(self):
        for fields in (
            [("sort[2]", "1"), ("name[2]", "已有")],
            [("sort[2]", "2"), ("name[2]", "未保存的改名")],
            [("id[4]", "999"), ("sort[4]", "4"), ("name[4]", "已有")],
            [("sort[4]", "4"), ("name[4]", "已有")],
            [("id[4]", "2"), ("name[4]", "已有")],
        ):
            site = CategorySite([dict(id="2", name="已有")], fields)
            with self.assertRaises(CategoryError):
                ensure_personal_category(site, "AI")
            self.assertEqual(site.writes, [])

    def test_id_encoded_in_field_name_is_preserved(self):
        fields = [("sort[42]", "1"), ("name[42]", "已有")]
        site = CategorySite([dict(id="42", name="已有")], fields)
        ensure_personal_category(site, "AI")
        self.assertEqual(site.writes[0][:2], fields)

    def test_lost_or_renamed_existing_category_after_save_stops(self):
        for mutation in (lambda site: site.items.pop(0), lambda site: site.items[0].update(name="意外改名")):
            site = CategorySite([dict(id="42", name="已有")], [("id[4]", "42"), ("sort[4]", "4"), ("name[4]", "已有")])
            save = site.save
            def altered_save(fields):
                result = save(fields)
                mutation(site)
                return result
            site.save = altered_save
            with self.assertRaises(CategoryError):
                ensure_personal_category(site, "AI")
            self.assertEqual(len(site.writes), 1)
            self.assertIsNone(site.refreshed)

    def test_query_failure_never_opens_manager_or_writes(self):
        site = CategorySite()
        site.categories = Mock(side_effect=CategoryError("login unavailable"))
        site.manager = Mock(side_effect=AssertionError("must not open manager"))
        with self.assertRaises(CategoryError):
            ensure_personal_category(site, "AI")
        self.assertEqual(site.writes, [])
        site.manager.assert_not_called()

    def test_confirmation_query_failure_does_not_repeat_write(self):
        site = CategorySite(fields=[("sort[]", "1"), ("name[]", "")])
        original_query = site.categories
        def query():
            if site.writes:
                raise CategoryError("response unavailable")
            return original_query()
        site.categories = query
        with self.assertRaises(CategoryError):
            ensure_personal_category(site, "AI")
        self.assertEqual(len(site.writes), 1)
        self.assertIsNone(site.refreshed)


class CategoryClientTests(unittest.TestCase):
    def test_login_or_malformed_response_is_rejected(self):
        for response in (
            None, {"status": -9}, {"status": 1, "data": {}},
            {"status": True, "data": {"custom": []}},
            {"status": 1, "data": {"custom": [{"custom_id": None, "name": "AI"}]}},
        ):
            with self.subTest(response=response):
                client = CategoryClient(None, Mock(evaluate=Mock(return_value=response)))
                with self.assertRaises(CategoryError):
                    client.categories()

    def test_names_are_decoded_and_ids_are_preserved(self):
        session = Mock(evaluate=Mock(return_value={"status": 1, "data": {"custom": [{"custom_id": 42, "name": "工程 &amp; 实践"}]}}))
        self.assertEqual(CategoryClient(None, session).categories(), [dict(id="42", name="工程 & 实践")])

    def test_form_waits_for_existing_names_to_render(self):
        session = Mock(evaluate=Mock(side_effect=[[], [["sort[4]", "4"], ["name[4]", "已有"]]]))
        with patch("blogpost.publishers.personal_categories.time.sleep"):
            fields = CategoryClient(None, session).form([dict(id="42", name="已有")])
        self.assertEqual(fields, [("sort[4]", "4"), ("name[4]", "已有")])

    def test_missing_editor_list_stops(self):
        with self.assertRaises(CategoryError):
            CategoryClient(None, Mock(evaluate=Mock(return_value=False))).refresh([dict(id="1", name="AI")])

    def test_form_retries_read_only_during_navigation(self):
        session = Mock(evaluate=Mock(side_effect=[RuntimeError("context destroyed"), [["sort[]", "1"], ["name[]", ""]]]))
        with patch("blogpost.publishers.personal_categories.time.sleep"):
            fields = CategoryClient(None, session).form([])
        self.assertEqual(fields, [("sort[]", "1"), ("name[]", "")])


if __name__ == "__main__":
    unittest.main()
