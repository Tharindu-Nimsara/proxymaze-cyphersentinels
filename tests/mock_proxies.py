"""
Mock proxy server for local testing.
Exposes /proxy/px-101 ... /proxy/px-110 endpoints.
Toggle each proxy alive/dead via /admin/kill/{id} and /admin/heal/{id}.
Run: python tests/mock_proxies.py
"""
from fastapi import FastAPI, Response
import uvicorn

app = FastAPI()

# In-memory state of which proxies are "alive"
proxy_state = {f"px-{i}": True for i in range(101, 121)}


@app.get("/proxy/{pid}")
async def proxy(pid: str):
    if pid not in proxy_state:
        return Response(status_code=404)
    if proxy_state[pid]:
        return {"id": pid, "status": "ok"}
    else:
        # Simulate downstream failure
        return Response(status_code=503)


@app.post("/admin/kill/{pid}")
async def kill(pid: str):
    proxy_state[pid] = False
    return {"id": pid, "alive": False}


@app.post("/admin/heal/{pid}")
async def heal(pid: str):
    proxy_state[pid] = True
    return {"id": pid, "alive": True}


@app.get("/admin/state")
async def get_state():
    return proxy_state


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
