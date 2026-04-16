import asyncio
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
async def startup():
    print("LOOP POLICY:", asyncio.get_event_loop_policy())
    print("LOOP TYPE:", type(asyncio.get_running_loop()))
