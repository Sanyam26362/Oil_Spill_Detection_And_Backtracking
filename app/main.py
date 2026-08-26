# app/main.py
from fastapi import FastAPI

app = FastAPI(
    title="Oil Spill Hindcasting & Attribution Engine",
    description="Automated drift hindcasting and AIS vessel attribution system.",
    version="1.0.0"
)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "online",
        "system": "SIH26143 Attribution Engine",
        "region": "Eastern Mediterranean (DARTIS 2019)"
    }