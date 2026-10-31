# For graders: how to run SilverFile

Every step below was run from a fresh clone (see [fresh-clone-test.md](fresh-clone-test.md)).

## 0. What you need
- Git, and either **Docker Desktop** (easiest) or **Python 3.11**.
- Optional: your own **OpenAI or Anthropic API key**. It is only used to read a W-2 photo with AI;
  everything else works without one.

## 1. Get the code
```
git clone https://github.com/franitaa/multiagent-tax-system.git
cd multiagent-tax-system
cp .env.example .env
```
To read W-2 photos, put your key after `OPENAI_API_KEY=` or `ANTHROPIC_API_KEY=` in `.env` and save it
**before starting the app** (the key is read once, at start). `.env` is never committed.

## 2. Start the app (pick one)
**A. Docker:**
```
docker compose up --build            # stop with: docker compose down   (-v also deletes saved cases)
```
**B. Python 3.11:**
```
python3.11 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```
Open **http://localhost:8501**: the start page, with **I'm a taxpayer** and **I'm a Kushim volunteer**.
Both ways publish the app on this computer only (the volunteer dashboard and `/telemetry` have no login).

## 3. Automatic checks (no key needed)
With Docker, run them as `docker compose exec app python …`; with Python, in the virtual environment.
| Command | What you should see |
|---|---|
| `python run.py check` | the test suite (`… passed`, no failures) and the eval cases (`15 pass, 0 fail, 0 pending`) |
| `python run.py demo` | the agent route for a clean case, then `DRAFT READY (nothing was filed)` |
| `python run.py demo spouse-died` | `INTERRUPT (FILING_STATUS_AMBIGUITY)`, the volunteer's decision, then `DRAFT READY` |

## 4. The two demo cases (assignment §5.2)
Follow [demo/eval_case_1.md](../demo/eval_case_1.md) (clean run) and
[demo/eval_case_2.md](../demo/eval_case_2.md) (a volunteer event, resolved). In short:
- **Case 1:** I'm a taxpayer → Start a new session → answer the 24 questions (the file lists them); at
  "Did you get a W-2 form?" → yes, add [`demo/w2_image_1.jpg`](../demo/w2_image_1.jpg) → finish → I'm a
  Kushim volunteer → open the case → check the W-2 amounts → Accept → back in the chat: the draft 1040-SR,
  wages $30,000, refund $1,375. Click any amount to see its formula, inputs and source.
- **Case 2:** the same as widowed, with "Did a spouse pass away during 2025?" → yes and
  [`demo/w2_image_2.jpg`](../demo/w2_image_2.jpg); the volunteer resolves the filing status (married filing
  jointly, with a note), then checks the W-2; the draft is married filing jointly, deduction $33,100.

Without a key the W-2 step says a volunteer will help and the photo is not read; step 3 still shows
the whole pipeline.

## 5. More to look at
- **Telemetry (staff only, not linked):** http://localhost:8501/telemetry
- **An escalation:** in the chat, ask "Should I itemize?" (tax advice) or "My nephew is answering for
  me" (exploitation); the case pauses and appears on the volunteer dashboard.
- **Traces:** `traces/` (the `traces` volume in Docker), one JSONL file per case, field names only.
- **Docs:** the README (orchestration diagram, also as an image: [graph.png](graph.png); team and focus areas), [handoff-contract.md](handoff-contract.md)
  (what each agent reads and writes), [metrics.md](metrics.md) (context strategy),
  [policy.md](policy.md) (the rules corpus), [../evals/README.md](../evals/README.md) (eval cases).
