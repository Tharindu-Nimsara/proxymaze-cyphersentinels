import asyncio
import httpx
from state import state, now_iso
from alerts import evaluate_alert_state
from webhooks import dispatch_transitions

MAX_HISTORY_ENTRIES = 500


async def probe_one(client: httpx.AsyncClient, proxy: dict, timeout_s: float):
    url = proxy["url"]
    new_status = "down"

    try:
        resp = await client.get(url, timeout=timeout_s, follow_redirects=False)
        if 200 <= resp.status_code < 300:
            new_status = "up"
        elif 500 <= resp.status_code < 600:
            new_status = "down"
        elif 400 <= resp.status_code < 500:
            new_status = "up"
        else:
            new_status = "up"
    except (httpx.TimeoutException, httpx.ConnectError, httpx.ConnectTimeout,
            httpx.ReadTimeout, httpx.RemoteProtocolError, httpx.NetworkError,
            httpx.HTTPError):
        new_status = "down"
    except Exception:
        new_status = "down"

    checked_at = now_iso()
    proxy["status"] = new_status
    proxy["last_checked_at"] = checked_at
    proxy["total_checks"] = proxy.get("total_checks", 0) + 1

    if new_status == "down":
        proxy["consecutive_failures"] = proxy.get("consecutive_failures", 0) + 1
    else:
        proxy["consecutive_failures"] = 0

    proxy["up_count"] = proxy.get("up_count", 0) + (1 if new_status == "up" else 0)

    proxy["history"].append({"checked_at": checked_at, "status": new_status})
    if len(proxy["history"]) > MAX_HISTORY_ENTRIES:
        proxy["history"] = proxy["history"][-MAX_HISTORY_ENTRIES:]

    state.total_checks += 1


async def run_one_cycle():
    timeout_s = state.config["request_timeout_ms"] / 1000.0

    with state.lock:
        proxies_snapshot = list(state.proxies.values())

    if not proxies_snapshot:
        return

    async with httpx.AsyncClient() as client:
        tasks = [probe_one(client, p, timeout_s) for p in proxies_snapshot]
        await asyncio.gather(*tasks, return_exceptions=True)

    with state.lock:
        transitions = evaluate_alert_state()

    if transitions:
        await dispatch_transitions(transitions)


async def monitor_loop():
    while True:
        try:
            await run_one_cycle()
        except Exception as e:
            print(f"[monitor] cycle error: {e}")

        interval = state.config.get("check_interval_seconds", 15)
        interval = max(1, int(interval))
        await asyncio.sleep(interval)
