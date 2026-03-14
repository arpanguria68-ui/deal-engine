"""Direct runner for DealForge AI backend.
Runs uvicorn in-process (no subprocess spawning) to avoid
Windows Defender blocking child process creation.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        # NO reload=True — that spawns a subprocess which gets blocked
    )
