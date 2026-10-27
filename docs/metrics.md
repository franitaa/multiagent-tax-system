# Context-window measurement

Actual API measurements are pending. No counts have been fabricated.

After setup, run:

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_context.py --compare
```

The command prompts securely for a key and makes 20 paid calls: the same ten synthetic W-2 images with accumulated history, then with selective recall. Each run processes ten images sequentially in one LangGraph thread. Full evidence remains in state; selective recall sends only the current image and a compact summary.

The command replaces this file with real API input-token counts and saves raw data under `runtime/benchmark/`. Counts include image/schema/system input, so the image-token floor can dominate. Inspect results before claiming a materially flatter curve. This is a measurement-only graph; it never approves records or produces a return.

Use `--no-context-strategy` for only the baseline. With neither flag, only the enabled strategy runs. Missing comparison cells remain blank.
