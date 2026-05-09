import asyncio
import uuid
from urllib.parse import urlparse
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from state import state, now_iso as _now_iso
from monitor import monitor_loop
from alerts import compute_pool_stats
from webhooks import dispatch_transitions


def extract_proxy_id(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return url
    segments = [s for s in path.split("/") if s]
    return segments[-1] if segments else url


def serialize_proxy_summary(p: dict) -> dict:
    return {
        "id": p["id"],
        "url": p["url"],
        "status": p["status"],
        "last_checked_at": p.get("last_checked_at"),
        "consecutive_failures": p.get("consecutive_failures", 0),
    }


def serialize_proxy_detail(p: dict) -> dict:
    total = p.get("total_checks", 0)
    up_count = p.get("up_count", 0)
    uptime = round((up_count / total * 100), 1) if total > 0 else 0.0
    return {
        "id": p["id"],
        "url": p["url"],
        "status": p["status"],
        "last_checked_at": p.get("last_checked_at"),
        "consecutive_failures": p.get("consecutive_failures", 0),
        "total_checks": total,
        "uptime_percentage": uptime,
        "history": p.get("history", []),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(monitor_loop())
    yield
    task.cancel()


app = FastAPI(title="ProxyMaze", lifespan=lifespan)


async def parse_body(request: Request) -> dict:
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        return body
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/config")
async def set_config(request: Request):
    body = await parse_body(request)

    interval = body.get("check_interval_seconds")
    timeout_ms = body.get("request_timeout_ms")

    with state.lock:
        if interval is not None:
            try:
                state.config["check_interval_seconds"] = max(1, int(interval))
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="invalid check_interval_seconds")
        if timeout_ms is not None:
            try:
                state.config["request_timeout_ms"] = max(1, int(timeout_ms))
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="invalid request_timeout_ms")

    return JSONResponse(status_code=200, content=dict(state.config))


@app.get("/config")
async def get_config():
    with state.lock:
        return dict(state.config)


@app.post("/proxies")
async def add_proxies(request: Request):
    body = await parse_body(request)

    proxies_in = body.get("proxies", [])
    if not isinstance(proxies_in, list):
        raise HTTPException(status_code=400, detail="proxies must be a list")

    replace = bool(body.get("replace", False))

    accepted_list = []
    transitions = []
    with state.lock:
        if replace:
            state.proxies.clear()
            if state.active_alert is not None:
                alert = state.active_alert
                alert["status"] = "resolved"
                alert["resolved_at"] = _now_iso()
                state.active_alert = None
                transitions.append({"event": "alert.resolved", "alert": alert})

        for url in proxies_in:
            if not isinstance(url, str) or not url:
                continue
            pid = extract_proxy_id(url)
            existing = state.proxies.get(pid)
            if existing is not None and not replace:
                accepted_list.append({
                    "id": pid,
                    "url": existing["url"],
                    "status": existing["status"],
                })
                continue
            state.proxies[pid] = {
                "id": pid,
                "url": url,
                "status": "pending",
                "last_checked_at": None,
                "consecutive_failures": 0,
                "total_checks": 0,
                "up_count": 0,
                "history": [],
            }
            accepted_list.append({
                "id": pid,
                "url": url,
                "status": "pending",
            })

    if transitions:
        await dispatch_transitions(transitions)

    return JSONResponse(
        status_code=201,
        content={"accepted": len(accepted_list), "proxies": accepted_list},
    )


@app.get("/proxies")
async def list_proxies():
    with state.lock:
        total, up, down, failure_rate, _ = compute_pool_stats()
        proxy_summaries = [serialize_proxy_summary(p) for p in state.proxies.values()]

    return {
        "total": total,
        "up": up,
        "down": down,
        "failure_rate": failure_rate,
        "proxies": proxy_summaries,
    }


@app.get("/proxies/{proxy_id}")
async def get_proxy(proxy_id: str):
    with state.lock:
        p = state.proxies.get(proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        return serialize_proxy_detail(p)


@app.get("/proxies/{proxy_id}/history")
async def get_proxy_history(proxy_id: str):
    with state.lock:
        p = state.proxies.get(proxy_id)
        if p is None:
            raise HTTPException(status_code=404, detail="proxy not found")
        return list(p.get("history", []))


@app.delete("/proxies", status_code=204)
async def delete_proxies():
    transitions = []
    with state.lock:
        state.proxies.clear()
        if state.active_alert is not None:
            alert = state.active_alert
            alert["status"] = "resolved"
            alert["resolved_at"] = _now_iso()
            state.active_alert = None
            transitions.append({"event": "alert.resolved", "alert": alert})
    if transitions:
        await dispatch_transitions(transitions)
    return Response(status_code=204)


@app.get("/alerts")
async def get_alerts():
    with state.lock:
        return [dict(a) for a in state.alerts]


@app.post("/webhooks")
async def register_webhook(request: Request):
    body = await parse_body(request)
    url = body.get("url")
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="url is required")

    webhook_id = f"wh-{uuid.uuid4().hex[:8]}"
    record = {"webhook_id": webhook_id, "url": url}

    with state.lock:
        state.webhooks.append(record)

    return JSONResponse(status_code=201, content=record)


@app.post("/integrations")
async def register_integration(request: Request):
    body = await parse_body(request)

    integ_type = body.get("type")
    webhook_url = body.get("webhook_url")

    if integ_type not in ("slack", "discord"):
        raise HTTPException(status_code=400, detail="type must be 'slack' or 'discord'")
    if not webhook_url or not isinstance(webhook_url, str):
        raise HTTPException(status_code=400, detail="webhook_url is required")

    record = {
        "integration_id": f"int-{uuid.uuid4().hex[:8]}",
        "type": integ_type,
        "webhook_url": webhook_url,
        "username": body.get("username") or "ProxyWatch",
        "events": body.get("events") or ["alert.fired", "alert.resolved"],
    }

    with state.lock:
        state.integrations.append(record)

    return JSONResponse(status_code=201, content=record)


@app.get("/metrics")
async def get_metrics():
    with state.lock:
        active_count = 1 if state.active_alert is not None else 0
        return {
            "total_checks": state.total_checks,
            "current_pool_size": len(state.proxies),
            "active_alerts": active_count,
            "total_alerts": len(state.alerts),
            "webhook_deliveries": state.webhook_deliveries,
        }


@app.get("/")
async def root():
    return {"service": "ProxyMaze", "version": "1.0.0"}
