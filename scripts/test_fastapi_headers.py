import sys
import uvicorn
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from threading import Thread
import time
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/deals/{deal_id}/report")
def generate_deal_report(deal_id: str, format: str = "pdf"):
    filename = f"DealForge_Something.{format}"
    return Response(
        content=b"test",
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def run():
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="error")


def test():
    time.sleep(1)
    url = "http://127.0.0.1:9000/api/v1/deals/80fb01f5-cb56-47b9-a84b-9e00854921e5/report?format=pdf"
    r = requests.get(url)
    print("STATUS:", r.status_code)
    print("HEADERS:", dict(r.headers))
    # Test if it redirects or anything
    print("URL:", r.url)


if __name__ == "__main__":
    t = Thread(target=run, daemon=True)
    t.start()
    test()
