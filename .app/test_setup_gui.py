import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

APP_DIR = Path(__file__).resolve().parent

class SetupGuiSecurityTests(unittest.TestCase):
    def test_setup_gui_powershell_absolute_path(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        with patch.dict("os.environ", {"SystemRoot": r"C:\Poisoned", "PATH": r"C:\Poisoned"}):
            with patch('subprocess.Popen') as mock_popen:
                dummy_process = MagicMock()
                dummy_process.returncode = 0
                dummy_process.stdout = []
                mock_popen.return_value = dummy_process

                class DummyApp:
                    def after(self, *args):
                        pass
                    def _append(self, *args):
                        pass
                    def _finish(self, *args):
                        pass

                    _get_system_executable = setup_gui.SetupApp._get_system_executable

                dummy_self = DummyApp()

                # Mocking SETUP_PS1 so it won't crash when it checks .exists()
                # or wait... _run_setup just converts to str(SETUP_PS1), it doesn't check exist?
                # Let's see why mock_popen wasn't called. Maybe an exception happened!

                try:
                    setup_gui.SetupApp._run_setup(dummy_self)
                except Exception as e:
                    print(f"Exception calling _run_setup: {e}")

                mock_popen.assert_called_once()
                cmd = mock_popen.call_args[0][0][0]

                self.assertTrue(cmd.lower().endswith("powershell.exe"))
                self.assertNotIn("poisoned", cmd.lower())
                self.assertTrue("system32" in cmd.lower())
                self.assertTrue(os.path.isabs(cmd) or cmd.startswith("C:\\") or cmd.startswith("c:\\"))

    def test_setup_gui_path_traversal(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        class DummyApp:
            _get_system_executable = setup_gui.SetupApp._get_system_executable

        dummy_self = DummyApp()

        with self.assertRaises(ValueError):
            dummy_self._get_system_executable("../cmd.exe")

        with self.assertRaises(ValueError):
            dummy_self._get_system_executable("System32/../../cmd.exe")

    def test_setup_gui_path_traversal_false_positive(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        class DummyApp:
            _get_system_executable = setup_gui.SetupApp._get_system_executable

        dummy_self = DummyApp()

        # file..exe should not trigger the traversal check
        result = dummy_self._get_system_executable("file..exe")
        self.assertTrue(result.endswith("file..exe") or "cmd.exe" in result)

    def test_setup_gui_open_url_validation(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        class DummyApp:
            _open = setup_gui.SetupApp._open

        dummy_self = DummyApp()

        with patch("webbrowser.open") as mock_web_open:
            with patch("os.startfile", create=True) as mock_startfile:
                # Dangerous or invalid URLs should be ignored
                dummy_self._open("calc.exe")
                dummy_self._open("file:///C:/Windows/notepad.exe")
                dummy_self._open("ftp://example.com")
                dummy_self._open(None)

                mock_startfile.assert_not_called()
                mock_web_open.assert_not_called()

                # Valid HTTP/HTTPS URLs should proceed
                dummy_self._open("https://www.python.org/downloads/")
                self.assertTrue(mock_startfile.called or mock_web_open.called)

    def test_setup_gui_result_file_reading(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            res_file = Path(tmpdir) / "setup-result.txt"
            res_file.write_text("STATUS=0\nSetup concluído com sucesso.", encoding="utf-8")

            with patch.object(setup_gui, "RESULT_FILE", res_file):
                with patch("subprocess.Popen") as mock_popen:
                    dummy_process = MagicMock()
                    dummy_process.returncode = 0
                    dummy_process.stdout = MagicMock()
                    dummy_process.stdout.readline.side_effect = ["Executando setup...\n", ""]
                    mock_popen.return_value = dummy_process

                    class DummyApp:
                        def after(self, ms, func, *args):
                            func(*args)

                        def _append(self, text):
                            pass

                        def _finish(self, code, msg):
                            self.finished_code = code
                            self.finished_msg = msg

                        _get_system_executable = setup_gui.SetupApp._get_system_executable
                        _run_setup = setup_gui.SetupApp._run_setup

                    dummy_self = DummyApp()
                    dummy_self._run_setup()

                    self.assertEqual(getattr(dummy_self, "finished_code", None), 0)
                    self.assertEqual(getattr(dummy_self, "finished_msg", None), "Setup concluído com sucesso.")

    def test_setup_gui_symlink_parent_dir_support(self):
        spec = importlib.util.spec_from_file_location("setup_gui", APP_DIR / "setup_gui.py")
        setup_gui = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup_gui)

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            real_dir = Path(tmpdir) / "real_app"
            real_dir.mkdir()
            ps1_file = real_dir / "setup.ps1"
            ps1_file.write_text("Write-Output 'OK'", encoding="utf-8")

            link_dir = Path(tmpdir) / "linked_app"
            try:
                os.symlink(real_dir, link_dir, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported in environment")

            symlinked_ps1 = link_dir / "setup.ps1"
            with patch.object(setup_gui, "SETUP_PS1", symlinked_ps1):
                class DummyApp:
                    def _set_status(self, *args):
                        pass
                    def _append(self, *args):
                        pass
                    def _start_bar(self, *args):
                        pass
                    def _finish(self, code, msg):
                        self.finished_code = code
                        self.finished_msg = msg
                    def _run_setup(self):
                        pass

                    _start = setup_gui.SetupApp._start

                dummy_self = DummyApp()
                with patch("threading.Thread") as mock_thread:
                    dummy_self._start()
                    # Verify _start succeeds and starts worker thread for legitimate symlinked parent path
                    mock_thread.assert_called_once()

if __name__ == "__main__":
    unittest.main()
