from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio

# Replace this with your actual pipeline integration.
# Option 1 (recommended): import a function from your pipeline module
# def run_pipeline(prompt: str, session_id: Optional[str] = None) -> str:
#     ...

# Option 2: manage a subprocess that writes to stdin and reads from stdout.
# For now, we keep a stub so the API runs; wire it up later.

app = FastAPI(title="Knowledge-and-Language Chat API")


class ChatRequest(BaseModel):
    prompt: str
    sessionId: Optional[str] = None
    history: Optional[list] = None  # if you want to pass convo context


class ChatResponse(BaseModel):
    reply: str
    metadata: Optional[Dict[str, Any]] = None


# Simple mutex to serialize access to the pipeline if it's single-threaded.
lock = asyncio.Lock()


async def run_pipeline_stub(prompt: str, session_id: Optional[str] = None) -> str:
    # TODO: Replace this with actual pipeline call.
    # Example if you have a function:
    # return run_pipeline(prompt, session_id)
    await asyncio.sleep(0.1)
    return f"[stub] You said: {prompt}"


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt must not be empty")

    async with lock:
        try:
            reply = await run_pipeline_stub(req.prompt, req.sessionId)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    return ChatResponse(reply=reply, metadata={"sessionId": req.sessionId})


# Health endpoint to check readiness
@app.get("/api/health")
async def health():
    return {"status": "ok", "pipeline": "stub"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
