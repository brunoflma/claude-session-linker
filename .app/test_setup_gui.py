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

if __name__ == "__main__":
    unittest.main()
