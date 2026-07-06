import importlib.util
import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("session_linker.py")
spec = importlib.util.spec_from_file_location("session_linker", MODULE_PATH)
session_linker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session_linker)


CLAUDE_DIR_ENV = "CLAUDE_SESSION_LINKER_CLAUDE_DIR"


def load_session_linker_with_env(appdata: Path, localappdata: Path, claude_dir: Path | None = None):
    original_appdata = os.environ.get("APPDATA")
    original_localappdata = os.environ.get("LOCALAPPDATA")
    original_claude_dir = os.environ.get(CLAUDE_DIR_ENV)
    os.environ["APPDATA"] = str(appdata)
    os.environ["LOCALAPPDATA"] = str(localappdata)
    if claude_dir is None:
        os.environ.pop(CLAUDE_DIR_ENV, None)
    else:
        os.environ[CLAUDE_DIR_ENV] = str(claude_dir)
    try:
        env_spec = importlib.util.spec_from_file_location("session_linker_env_test", MODULE_PATH)
        module = importlib.util.module_from_spec(env_spec)
        env_spec.loader.exec_module(module)
        return module
    finally:
        if original_appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = original_appdata
        if original_localappdata is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = original_localappdata
        if original_claude_dir is None:
            os.environ.pop(CLAUDE_DIR_ENV, None)
        else:
            os.environ[CLAUDE_DIR_ENV] = original_claude_dir


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


def write_code_session(root: Path, account_id: str, workspace_id: str, name: str, cli_id: str, last_activity: int):
    workspace = root / "claude-code-sessions" / account_id / workspace_id
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"local_{name}.json"
    path.write_text(
        json.dumps({
            "sessionId": name,
            "cliSessionId": cli_id,
            "cwd": rf"C:\project\{name}",
            "title": name,
            "lastActivityAt": last_activity,
        }),
        encoding="utf-8",
    )
    return path


def write_cowork_session(root: Path, account_id: str, workspace_id: str, name: str, cli_id: str, last_activity: int):
    workspace = root / "local-agent-mode-sessions" / account_id / workspace_id
    data_dir = workspace / f"local_{name}"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "audit.jsonl").write_text('{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
    path = workspace / f"local_{name}.json"
    path.write_text(
        json.dumps({
            "sessionId": name,
            "cliSessionId": cli_id,
            "cwd": rf"C:\project\{name}",
            "title": name,
            "lastActivityAt": last_activity,
        }),
        encoding="utf-8",
    )
    return path, data_dir


class SessionLinkerLogicTests(unittest.TestCase):
    def test_module_uses_explicit_claude_profile_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            explicit_root = Path(tmp) / "PinnedClaude"

            module = load_session_linker_with_env(appdata, localappdata, explicit_root)

            self.assertEqual(module.CLAUDE_DIR, explicit_root)

    def test_module_uses_newest_valid_claude_profile_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "claude-code-sessions").mkdir(parents=True)
            (custom_root / "claude-code-sessions").mkdir(parents=True)
            default_config = default_root / "config.json"
            custom_config = custom_root / "config.json"
            default_config.write_text("{}", encoding="utf-8")
            custom_config.write_text("{}", encoding="utf-8")
            old_ts = time.time() - 300
            new_ts = time.time()
            os.utime(default_config, (old_ts, old_ts))
            os.utime(custom_config, (new_ts, new_ts))

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, custom_root)
            self.assertEqual(module.CLAUDE_DIRS, [custom_root, default_root])
            self.assertEqual(module.SESSIONS_DIR, custom_root / "claude-code-sessions")
            self.assertEqual(module.COWORK_SESSIONS_DIR, custom_root / "local-agent-mode-sessions")
            self.assertEqual(module.CONFIG_JSON, custom_root / "config.json")

    def test_scan_sessions_includes_accounts_from_all_valid_claude_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "config.json").parent.mkdir(parents=True)
            (custom_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            write_code_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            write_code_session(custom_root, "threep-account", "workspace-3p", "threep", "cli-3p", 20)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_sessions()

            self.assertEqual(set(sessions), {"official-account", "threep-account"})
            self.assertEqual(sessions["official-account"][0]["claudeDir"], default_root)
            self.assertEqual(sessions["threep-account"][0]["claudeDir"], custom_root)

    def test_scan_cowork_sessions_includes_accounts_from_all_valid_claude_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            (default_root / "config.json").parent.mkdir(parents=True)
            (custom_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")
            write_cowork_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            _, custom_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "threep", "cli-3p", 20)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_cowork_sessions()

            self.assertEqual(set(sessions), {"official-account", "threep-account"})
            self.assertEqual(sessions["official-account"][0]["claudeDir"], default_root)
            self.assertEqual(sessions["threep-account"][0]["claudeDir"], custom_root)
            self.assertEqual(sessions["threep-account"][0]["data_dir"], custom_data_dir)

    def test_scan_cowork_sessions_ignores_empty_non_account_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            (default_root / "config.json").parent.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            write_cowork_session(default_root, "official-account", "workspace-official", "official", "cli-official", 10)
            (default_root / "local-agent-mode-sessions" / "skills-plugin" / "workspace").mkdir(parents=True)

            module = load_session_linker_with_env(appdata, localappdata)
            sessions = module.scan_cowork_sessions()

            self.assertEqual(set(sessions), {"official-account"})

    def test_link_session_to_account_can_copy_from_3p_root_to_official_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path = write_code_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "claude-code-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            default_config = default_root / "config.json"
            custom_config = custom_root / "config.json"
            default_config.write_text("{}", encoding="utf-8")
            custom_config.write_text("{}", encoding="utf-8")
            old_ts = time.time() - 300
            new_ts = time.time()
            os.utime(default_config, (old_ts, old_ts))
            os.utime(custom_config, (new_ts, new_ts))

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertFalse((custom_root / "claude-code-sessions" / "official-account").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_link_session_to_account_can_copy_from_official_root_to_3p_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path = write_code_session(default_root, "official-account", "workspace-official", "source", "cli-source", 20)
            target_workspace = custom_root / "claude-code-sessions" / "threep-account" / "workspace-3p"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "accountId": "official-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_session_to_account(source_session, "threep-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertFalse((default_root / "claude-code-sessions" / "threep-account").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_link_cowork_session_to_account_can_copy_between_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            custom_root = localappdata / "Claude-3p"
            source_path, source_data_dir = write_cowork_session(custom_root, "threep-account", "workspace-3p", "source", "cli-source", 20)
            target_workspace = default_root / "local-agent-mode-sessions" / "official-account" / "workspace-official"
            target_workspace.mkdir(parents=True)
            (default_root / "config.json").write_text("{}", encoding="utf-8")
            (custom_root / "config.json").write_text("{}", encoding="utf-8")

            module = load_session_linker_with_env(appdata, localappdata)
            original_links_file = module.LINKS_FILE
            original_backups_dir = module.BACKUPS_DIR
            module.LINKS_FILE = Path(tmp) / "session_links.json"
            module.BACKUPS_DIR = Path(tmp) / "backups"
            module.BACKUPS_DIR.mkdir()
            try:
                source_session = {
                    "path": source_path,
                    "data_dir": source_data_dir,
                    "accountId": "threep-account",
                    "originAccount": None,
                    "linkedFromAccount": None,
                }

                ok, message = module.link_cowork_session_to_account(source_session, "official-account")

                self.assertTrue(ok, message)
                self.assertTrue((target_workspace / source_path.name).exists())
                self.assertTrue((target_workspace / source_data_dir.name / "audit.jsonl").exists())
            finally:
                module.LINKS_FILE = original_links_file
                module.BACKUPS_DIR = original_backups_dir

    def test_remove_code_session_deletes_only_account_index_and_keeps_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path = write_code_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            transcript = Path(tmp) / "projects" / "workspace" / "cli-source.jsonl"
            transcript.parent.mkdir(parents=True)
            transcript.write_text('{"type":"user","timestamp":"2026-01-01T00:00:00Z"}\n', encoding="utf-8")
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "sessionsDir": root / "claude-code-sessions",
                        "title": "source",
                    },
                    "code",
                )

                self.assertTrue(ok, message)
                self.assertFalse(index_path.exists())
                self.assertTrue(transcript.exists())
                backups = list(session_linker.BACKUPS_DIR.glob("*.zip"))
                self.assertEqual(len(backups), 1)
                with zipfile.ZipFile(backups[0]) as zf:
                    self.assertIn(index_path.relative_to((root / "claude-code-sessions").parent).as_posix(), zf.namelist())
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_deletes_index_and_data_dir_after_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": data_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertTrue(ok, message)
                self.assertFalse(index_path.exists())
                self.assertFalse(data_dir.exists())
                backups = list(session_linker.BACKUPS_DIR.glob("*.zip"))
                self.assertEqual(len(backups), 1)
                with zipfile.ZipFile(backups[0]) as zf:
                    self.assertIn((index_path.parent.name + "/" + index_path.name), zf.namelist())
                    self.assertIn((index_path.parent.name + "/" + data_dir.name + "/audit.jsonl"), zf.namelist())
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_does_not_delete_index_if_data_dir_removal_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            links_file = Path(tmp) / "session_links.json"
            original_backups_dir = session_linker.BACKUPS_DIR
            original_links_file = session_linker.LINKS_FILE
            original_rmtree = session_linker.shutil.rmtree
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            session_linker.LINKS_FILE = links_file
            session_linker.record_link_metadata(index_path, "account-b", "account-a")
            session_linker.shutil.rmtree = lambda _path: (_ for _ in ()).throw(OSError("locked"))
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": data_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertFalse(ok, message)
                self.assertTrue(index_path.exists())
                self.assertTrue(data_dir.exists())
                self.assertIn(session_linker.LINKED_FROM_ACCOUNT_KEY, session_linker.get_link_metadata(index_path))
            finally:
                session_linker.shutil.rmtree = original_rmtree
                session_linker.LINKS_FILE = original_links_file
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_cowork_session_rejects_unexpected_data_dir_without_deleting_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path, data_dir = write_cowork_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            unsafe_dir = Path(tmp) / "elsewhere" / data_dir.name
            unsafe_dir.mkdir(parents=True)
            original_backups_dir = session_linker.BACKUPS_DIR
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "data_dir": unsafe_dir,
                        "sessionsDir": root / "local-agent-mode-sessions",
                        "title": "source",
                    },
                    "cowork",
                )

                self.assertFalse(ok, message)
                self.assertTrue(index_path.exists())
                self.assertTrue(data_dir.exists())
                self.assertTrue(unsafe_dir.exists())
                self.assertEqual(list(session_linker.BACKUPS_DIR.glob("*.zip")), [])
            finally:
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_remove_session_cleans_link_metadata_for_removed_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Claude"
            index_path = write_code_session(root, "account-a", "workspace-a", "source", "cli-source", 20)
            links_file = Path(tmp) / "session_links.json"
            original_backups_dir = session_linker.BACKUPS_DIR
            original_links_file = session_linker.LINKS_FILE
            session_linker.BACKUPS_DIR = Path(tmp) / "backups"
            session_linker.BACKUPS_DIR.mkdir()
            session_linker.LINKS_FILE = links_file
            session_linker.record_link_metadata(index_path, "account-b", "account-a")
            try:
                ok, message = session_linker.remove_session_from_account(
                    {
                        "path": index_path,
                        "sessionsDir": root / "claude-code-sessions",
                        "title": "source",
                    },
                    "code",
                )

                self.assertTrue(ok, message)
                self.assertEqual(session_linker.get_link_metadata(index_path), {})
            finally:
                session_linker.LINKS_FILE = original_links_file
                session_linker.BACKUPS_DIR = original_backups_dir

    def test_module_falls_back_to_roaming_claude_when_it_is_the_only_valid_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"
            default_root = appdata / "Claude"
            (default_root / "claude-code-sessions").mkdir(parents=True)
            (localappdata / "Claude-3p").mkdir(parents=True)

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, default_root)

    def test_module_keeps_legacy_roaming_path_when_no_valid_root_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            localappdata = Path(tmp) / "Local"

            module = load_session_linker_with_env(appdata, localappdata)

            self.assertEqual(module.CLAUDE_DIR, appdata / "Claude")

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

    def test_duplicate_detection_ignores_code_sessions_without_transcript_file(self):
        source = make_session("source", "source-cli", 10)
        missing = make_session("missing", "missing-cli", 8)
        original_find_transcript_path = session_linker.find_transcript_path
        session_linker.find_transcript_path = lambda cli_id: Path("found.jsonl") if cli_id == "source-cli" else None

        try:
            duplicates = session_linker.find_possible_duplicates(
                {
                    "account-a": [source],
                    "account-b": [missing],
                },
                mode="code",
            )
        finally:
            session_linker.find_transcript_path = original_find_transcript_path

        self.assertEqual(duplicates, {})

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
