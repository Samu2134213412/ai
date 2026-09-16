# Verify it on your own PC

The build machine had Claude Code, Python, Node and Git — but **no Ollama, no
GPU and no Qwen model**, so the Ollama half of the stack could not be exercised
there (see `PROJECT_STATUS.md`). This is the checklist that closes that gap.
Ten minutes, and nothing here touches a real repository.

Tick each box. If one fails, the section says what it means.

## 1. Ollama serves the Anthropic API

```powershell
ollama --version           # must be 0.14.0 or newer
curl http://127.0.0.1:11434/api/tags
```

```powershell
curl -X POST http://127.0.0.1:11434/v1/messages ^
  -H "Content-Type: application/json" ^
  -H "x-api-key: ollama" ^
  -H "anthropic-version: 2023-06-01" ^
  -d "{\"model\":\"qwen3-coder:30b\",\"max_tokens\":64,\"messages\":[{\"role\":\"user\",\"content\":\"Say PONG\"}]}"
```

- [ ] You get JSON with a `content` array containing `PONG`.

*Fails?* Either Ollama is older than 0.14.0 (update it) or the model is not
pulled (`ollama pull qwen3-coder:30b`). Nothing else will work until this passes.

## 2. CodePilot sees everything

```powershell
start.bat --check
```

- [ ] Claude Code: Available
- [ ] Git: Available
- [ ] Ollama: Online
- [ ] Model: qwen3-coder:30b — Available

*Fails?* The output prints the exact remedy for whatever is missing.

## 3. Claude Code actually thinks with the local model

This is the step that proves the integration, independent of CodePilot.

```powershell
set ANTHROPIC_BASE_URL=http://127.0.0.1:11434
set ANTHROPIC_AUTH_TOKEN=ollama
set ANTHROPIC_API_KEY=
set ANTHROPIC_DEFAULT_SONNET_MODEL=qwen3-coder:30b
set ANTHROPIC_DEFAULT_OPUS_MODEL=qwen3-coder:30b
set ANTHROPIC_DEFAULT_HAIKU_MODEL=qwen3-coder:30b
claude --print --model qwen3-coder:30b "Reply with exactly: PONG"
```

- [ ] It prints `PONG`.

*Fails with a timeout or a hang?* That is
[ollama/ollama#13949](https://github.com/ollama/ollama/issues/13949) — the
`count_tokens` problem. Leave CodePilot's compatibility proxy **on** (the
default) and it will not affect you when going through CodePilot.

## 4. The full stack, through CodePilot

Make a throwaway repo — **not** Agent Factory:

```powershell
mkdir %USERPROFILE%\codepilot-demo && cd %USERPROFILE%\codepilot-demo
git init
echo def add(a, b):> calc.py
echo     return a + b>> calc.py
git add -A && git commit -m initial
```

Then:

1. Start CodePilot, add `%USERPROFILE%\codepilot-demo` on the Projects page.
2. Pair your phone.
3. New task: *"Add subtract(a, b) to calc.py and a unit test for it, then run
   `python -m pytest -q`."*

- [ ] The session screen streams `TOOL Read`, `TOOL Edit`, `TOOL Bash` in near real time
- [ ] An approval card appears for the `pytest` command, and tapping **Approve Once** lets it run
- [ ] `TESTS` shows a pass/fail summary
- [ ] **View changes** lists `calc.py` with `+n / -m`, and the diff opens
- [ ] The session ends as `completed`
- [ ] Killing the app mid-task and reopening it shows everything you missed
- [ ] `calc.py` on disk really contains `subtract`

## 5. Remote access

- [ ] With Tailscale up on both devices, turn **off** the phone's Wi-Fi and open
      the app — it reconnects on the `100.x.y.z` address (check **Connection**).
- [ ] Start a task, close the app, wait a minute, reopen it: the transcript is
      complete.

## 6. The automated suite

```powershell
cd server
python -m pytest -q
set CODEPILOT_LIVE_CLAUDE=1
set CODEPILOT_LIVE_USE_OLLAMA=1
set CODEPILOT_LIVE_MODEL=qwen3-coder:30b
python -m pytest tests\test_integration_claude.py -v -s
```

The live test builds its own throwaway repo, drives a real Claude Code session
through the bridge, and independently re-runs the tests Claude Code wrote.

- [ ] The offline suite passes.
- [ ] The live test passes against `qwen3-coder:30b`.

*The live test fails but steps 1–3 passed?* The wiring is fine and the model is
the limit — a 30B local model is markedly weaker at long agentic tool chains than
a frontier model. Try a smaller task, and check the transcript to see where it
lost the thread.
