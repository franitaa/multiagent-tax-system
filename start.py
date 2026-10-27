"""One-command bootstrap: local virtual environment, dependencies, then the workbench."""
import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 11):
        print('Python 3.11 or later is required. This project was developed for Python 3.11/3.12.')
        return 1
    environment = ROOT / '.venv'
    executable = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not executable.exists():
        print('Creating the project Python environment…', flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    fingerprint = hashlib.sha256((ROOT / 'requirements.txt').read_bytes()
                                  + (ROOT / 'pyproject.toml').read_bytes()).hexdigest()
    stamp = environment / '.silverfile_setup'
    if not stamp.exists() or stamp.read_text() != fingerprint:
        print('Installing Python packages. This only repeats when requirements change…', flush=True)
        subprocess.run([str(executable), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')],
                       cwd=ROOT, check=True)
        stamp.write_text(fingerprint)
    print('Opening SilverFile at http://127.0.0.1:8501. Keep this terminal open.', flush=True)
    return subprocess.call([str(executable), '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                            '--server.address=127.0.0.1', '--server.port=8501', '--server.headless=true',
                            '--browser.gatherUsageStats=false'], cwd=ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError:
        print('Package installation failed. Check your internet connection and the error above.')
        raise SystemExit(1)
    except KeyboardInterrupt:
        print('\nSilverFile stopped. Saved cases remain in runtime/.')
