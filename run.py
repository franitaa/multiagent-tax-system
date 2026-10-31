"""One entry point for SilverFile. It only starts the project's existing commands.

  python run.py                   start the app: http://localhost:8501 (taxpayer chat, volunteer
                                  dashboard; staff telemetry at /telemetry)
  python run.py check             run the tests and the eval cases (no API key needed)
  python run.py demo              a clean case in the terminal, ending "DRAFT READY"
  python run.py demo spouse-died  eval case 2 in the terminal: pause for a volunteer, then a draft

Reading a W-2 photo in the app needs your own OpenAI or Anthropic key in .env (copy .env.example).
Docker instead: docker compose up --build (see the README).
"""
import subprocess
import sys

COMMANDS = {
    # on this computer only, like docker-compose.yml: the dashboard and /telemetry have no login
    "app": [["-m", "streamlit", "run", "src/ui/silverfile_home.py", "--server.address", "localhost"]],
    "check": [["-m", "pytest", "-q"], ["-m", "evals.runner"]],
    "demo": [["-m", "scripts.run_scenarios"]],
}


def main(argv: list[str]) -> int:
    what, rest = (argv[0], argv[1:]) if argv else ("app", [])
    if what not in COMMANDS:
        print(__doc__)
        return 2
    for command in COMMANDS[what]:
        args = command + (rest or (["clean"] if what == "demo" else []))
        code = subprocess.call([sys.executable, *args])
        if code:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
