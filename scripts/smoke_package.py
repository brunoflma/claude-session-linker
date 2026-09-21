"""Exercise an extracted package against synthetic profiles on a CI Windows/macOS runner."""
import argparse
import importlib.util
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from release_bundle import ROOT, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref', default='HEAD')
    parser.add_argument('--directory', type=Path, default=ROOT / 'release-artifacts')
    parser.add_argument('--gui', action='store_true')
    args = parser.parse_args()
    platform = 'windows' if sys.platform == 'win32' else 'macos' if sys.platform == 'darwin' else None
    if platform is None:
        raise RuntimeError('Package smoke check requires Windows or macOS')
    manifest, _ = verify_bundle(ROOT, args.ref, args.directory)
    archive = args.directory / f'claude-session-linker-{manifest["version"]}-{platform}.zip'
    with tempfile.TemporaryDirectory(prefix='csl-package-smoke-') as folder:
        base = Path(folder)
        extracted = base / 'app'
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)  # Byte-verified archive produced by the allowlisted builder above.
        profile = base / 'synthetic-claude'
        profile.mkdir()
        with patch.dict(os.environ, {'CLAUDE_SESSION_LINKER_CLAUDE_DIR': str(profile),
                                     'CLAUDE_SESSION_LINKER_PLATFORM': sys.platform}):
            spec = importlib.util.spec_from_file_location('release_smoke_linker', extracted / '.app/session_linker.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.CLAUDE_PROJECTS_DIR = base / 'synthetic-projects'
            assert module.APP_VERSION == manifest['version']
            assert module.scan_sessions() == {} and module.scan_cowork_sessions() == {}
            if args.gui:
                app = module.SessionLinkerApp()
                try:
                    app.withdraw()
                    app.update_idletasks()
                    app.update()
                    assert app.winfo_exists()
                finally:
                    app.destroy()
    print(json.dumps({'platform': platform, 'version': manifest['version'], 'commit': manifest['commit'], 'extracted_import': True, 'gui_checked': args.gui, 'real_profiles_used': False}))


if __name__ == '__main__':
    main()
