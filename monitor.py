import asyncio
import sys
import httpx
from state import state, now_iso
from alerts import evaluate_alert_state
from webhooks import dispatch_transitions

MAX_HISTORY_ENTRIES = 500


def _log(msg: str):
    print(f"[monitor] {msg}", flush=True, file=sys.stdout)


async def probe_one(client: httpx.AsyncClient, proxy_id: str, url: str, timeout_s: float):
    try:
        resp = await client.get(url, timeout=timeout_s, follow_redirects=True)
        status = "up" if 200 <= resp.status_code < 300 else "down"
        return proxy_id, status, resp.status_code
    except Exception as e:
        return proxy_id, "down", repr(e)[:60]


async def run_one_cycle(client: httpx.AsyncClient):
    timeout_s = state.config["request_timeout_ms"] / 1000.0

    with state.lock:
        targets = [(p["id"], p["url"]) for p in state.proxies.values()]

    if not targets:
        return 0, 0

    tasks = [probe_one(client, pid, url, timeout_s) for pid, url in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checked_at = now_iso()
    up_count = 0
    down_count = 0
    down_reasons = []
    with state.lock:
        for r in results:
            if isinstance(r, Exception):
                continue
            pid, new_status, reason = r
            if new_status == "down":
                down_reasons.append(f"{pid}={reason}")
            proxy = state.proxies.get(pid)
            if proxy is None:
                continue
            proxy["status"] = new_status
            proxy["last_checked_at"] = checked_at
            proxy["total_checks"] = proxy.get("total_checks", 0) + 1
            if new_status == "down":
                proxy["consecutive_failures"] = proxy.get("consecutive_failures", 0) + 1
                down_count += 1
            else:
                proxy["consecutive_failures"] = 0
                up_count += 1
            proxy["up_count"] = proxy.get("up_count", 0) + (1 if new_status == "up" else 0)
            proxy["history"].append({"checked_at": checked_at, "status": new_status})
            if len(proxy["history"]) > MAX_HISTORY_ENTRIES:
                proxy["history"] = proxy["history"][-MAX_HISTORY_ENTRIES:]
            state.total_checks += 1

        transitions = evaluate_alert_state()

    if down_reasons:
        _log(f"down reasons: {down_reasons[:5]}")

    if transitions:
        _log(f"transitions emitted: {[t['event'] for t in transitions]}")
        await dispatch_transitions(transitions)

    return up_count, down_count


async def monitor_loop():
    _log("background monitor started")
    cycle_num = 0
    while True:
        cycle_num += 1
        try:
            async with httpx.AsyncClient() as client:
                up, down = await run_one_cycle(client)
            if up + down > 0:
                _log(f"cycle {cycle_num}: up={up} down={down} total={up+down}")
        except Exception as e:
            _log(f"cycle {cycle_num} error: {e!r}")

        interval = max(1, int(state.config.get("check_interval_seconds", 5)))
        slept = 0
        while slept < interval:
            await asyncio.sleep(1)
            slept += 1
            interval = max(1, int(state.config.get("check_interval_seconds", 5)))
