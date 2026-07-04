import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("session_linker.py")
spec = importlib.util.spec_from_file_location("session_linker", MODULE_PATH)
session_linker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_linker)


def make_session(name, cli_id, last_activity, path_name=None):
    return {
        "path": Path(path_name or f"{name}.json"),
        "sessionId": name,
        "cliSessionId": cli_id,
        "cwd": r"C:\project",
        "title": name,
        "lastActivityAt": last_activity,
        "isArchived": False,
        "workspaceUUID": "workspace",
        "linkedFromAccount": None,
        "originAccount": None,
    }


class SessionLinkerLogicTests(unittest.TestCase):
    def test_compare_candidates_include_linked_copy_with_same_cli_id(self):
        source = make_session("source", "same-cli", 10, "local_source.json")
        linked_copy = make_session("linked", "same-cli", 8, "local_source.json")
        unrelated = make_session("unrelated", "other-cli", 20, "local_other.json")

        candidates = session_linker.build_compare_candidates(
            {
                "account-a": [source],
                "account-b": [linked_copy],
                "account-c": [unrelated],
            },
            "account-a",
            source,
        )

        self.assertEqual(candidates[0], ("account-b", linked_copy))
        self.assertIn(("account-c", unrelated), candidates)
        self.assertNotIn(("account-a", source), candidates)

    def test_linked_compare_targets_filter_out_unrelated_sessions(self):
        source = make_session("source", "same-cli", 10, "local_source.json")
        linked_copy = make_session("linked", "same-cli", 8, "local_source.json")
        unrelated = make_session("unrelated", "other-cli", 20, "local_other.json")
        candidates = [("account-b", linked_copy), ("account-c", unrelated)]

        targets = session_linker.linked_compare_targets(candidates, "account-a", source)

        self.assertEqual(targets, [("account-b", linked_copy)])

    def test_link_groups_detect_same_cli_id_across_accounts(self):
        source = make_session("source", "same-cli", 10)
        linked_copy = make_session("linked", "same-cli", 8)
        unrelated = make_session("unrelated", "other-cli", 20)

        groups = session_linker.find_linked_session_groups(
            {
                "account-a": [source],
                "account-b": [linked_copy],
                "account-c": [unrelated],
            }
        )

        self.assertEqual(groups["same-cli"], [("account-a", source), ("account-b", linked_copy)])
        self.assertNotIn("other-cli", groups)

    def test_copy_index_preserves_json_and_records_origin_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "local_source.json"
            dest = Path(tmp) / "local_dest.json"
            links_file = Path(tmp) / "session_links.json"
            original_links_file = session_linker.LINKS_FILE
            session_linker.LINKS_FILE = links_file
            original = {"sessionId": "source", "cliSessionId": "same-cli"}
            src.write_text(json.dumps(original), encoding="utf-8")

            try:
                session_linker.copy_index_with_link_metadata(src, dest, "account-a", "account-a")

                copied = json.loads(dest.read_text(encoding="utf-8"))
                self.assertEqual(copied, original)
                metadata = session_linker.get_link_metadata(dest)
                self.assertEqual(metadata[session_linker.LINKED_FROM_ACCOUNT_KEY], "account-a")
                self.assertEqual(metadata[session_linker.ORIGIN_ACCOUNT_KEY], "account-a")
                self.assertIn(session_linker.LINKED_AT_KEY, metadata)
            finally:
                session_linker.LINKS_FILE = original_links_file

    def test_existing_destination_updates_metadata_instead_of_failing(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "local_source.json"
            dest = Path(tmp) / "local_dest.json"
            links_file = Path(tmp) / "session_links.json"
            original_links_file = session_linker.LINKS_FILE
            session_linker.LINKS_FILE = links_file
            src.write_text(json.dumps({"sessionId": "source"}), encoding="utf-8")
            dest.write_text(json.dumps({"sessionId": "source"}), encoding="utf-8")

            try:
                copied = session_linker.ensure_index_linked(src, dest, "account-b", "account-a")

                self.assertFalse(copied)
                metadata = session_linker.get_link_metadata(dest)
                self.assertEqual(metadata[session_linker.LINKED_FROM_ACCOUNT_KEY], "account-b")
                self.assertEqual(metadata[session_linker.ORIGIN_ACCOUNT_KEY], "account-a")
            finally:
                session_linker.LINKS_FILE = original_links_file

    def test_source_origin_prefers_existing_origin_metadata(self):
        source = make_session("linked", "same-cli", 10)
        source["accountId"] = "account-b"
        source["originAccount"] = "account-a"

        self.assertEqual(session_linker.source_origin_account(source), "account-a")


if __name__ == "__main__":
    unittest.main()
