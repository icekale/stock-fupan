from fastapi import FastAPI

app = FastAPI(title="A 股每日复盘 API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
