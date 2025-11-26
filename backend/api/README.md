# Chat Backend (FastAPI)

This minimal backend exposes `/api/chat` to forward prompts from the React frontend to your pipeline.

## Install

```zsh
cd /home/ozzy/Desktop/mei/1ºano/1ºsemestre/CL/Knowledge-and-Language/src/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```zsh
source /home/ozzy/Desktop/mei/1ºano/1ºsemestre/CL/Knowledge-and-Language/src/backend/.venv/bin/activate
python server.py
```

Vite proxy already forwards `/api` to `http://localhost:8000`.

## Wire to your pipeline

Edit `server.py`:
- Replace `run_pipeline_stub` with your actual call.
- If your pipeline is a long-running process reading stdin and writing stdout, implement a subprocess manager and serialize access with the provided `lock`.
- If you can expose a function like `run_pipeline(prompt, session_id) -> str`, import and call it directly.

## Frontend usage

Submit prompts via:

```js
fetch('/api/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ prompt: userInput })
}).then(r => r.json()).then(({ reply }) => setMessages(m => [...m, { role: 'assistant', content: reply }]))
```

## Health check

- `GET /api/health` returns readiness status.