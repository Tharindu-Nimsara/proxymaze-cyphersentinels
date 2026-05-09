import asyncio
import sys
import httpx
from state import state
from integrations import format_slack, format_discord

TRANSIENT_FAILURE_CODES = {500, 502, 503, 504}
MAX_RETRY_DELAY = 5

_pending_tasks: set = set()


def _log(msg: str):
    print(f"[webhooks] {msg}", flush=True, file=sys.stdout)


def build_fired_payload(alert: dict) -> dict:
    return {
        "event": "alert.fired",
        "alert_id": alert["alert_id"],
        "fired_at": alert["fired_at"],
        "failure_rate": alert["failure_rate"],
        "total_proxies": alert["total_proxies"],
        "failed_proxies": alert["failed_proxies"],
        "failed_proxy_ids": alert["failed_proxy_ids"],
        "threshold": alert["threshold"],
        "message": alert["message"],
    }


def build_resolved_payload(alert: dict) -> dict:
    return {
        "event": "alert.resolved",
        "alert_id": alert["alert_id"],
        "resolved_at": alert["resolved_at"],
    }


async def deliver_once(client: httpx.AsyncClient, url: str, payload: dict) -> bool:
    try:
        resp = await client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        if 200 <= resp.status_code < 300:
            return True
        if resp.status_code in TRANSIENT_FAILURE_CODES:
            _log(f"transient {resp.status_code} from {url}")
            return False
        _log(f"non-transient {resp.status_code} from {url}: {resp.text[:200]}")
        return True
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as e:
        _log(f"net error to {url}: {e!r}")
        return False
    except Exception as e:
        _log(f"unexpected error to {url}: {e!r}")
        return False


async def deliver_with_retry(url: str, payload: dict, dedupe_key: tuple):
    with state.lock:
        if dedupe_key in state.delivered:
            return

    delay = 0.5
    attempt = 0
    try:
        async with httpx.AsyncClient() as client:
            while True:
                attempt += 1
                success = await deliver_once(client, url, payload)
                if success:
                    with state.lock:
                        if dedupe_key in state.delivered:
                            return
                        state.delivered.add(dedupe_key)
                        state.webhook_deliveries += 1
                    _log(f"delivered {dedupe_key[3]} -> {url} (attempt {attempt})")
                    return
                _log(f"retry {dedupe_key[3]} -> {url} (attempt {attempt}, delay {delay}s)")
                await asyncio.sleep(delay)
                delay = min(delay * 2, MAX_RETRY_DELAY)
    except Exception as e:
        _log(f"deliver_with_retry crashed for {url}: {e!r}")


async def dispatch_transitions(transitions: list):
    with state.lock:
        webhooks_snapshot = list(state.webhooks)
        integrations_snapshot = list(state.integrations)

    _log(f"dispatching {len(transitions)} transitions to {len(webhooks_snapshot)} webhooks, {len(integrations_snapshot)} integrations")

    for t in transitions:
        event_type = t["event"]
        alert = t["alert"]
        alert_id = alert["alert_id"]

        if event_type == "alert.fired":
            generic_payload = build_fired_payload(alert)
        else:
            generic_payload = build_resolved_payload(alert)

        for wh in webhooks_snapshot:
            key = ("generic", wh["webhook_id"], alert_id, event_type)
            task = asyncio.create_task(deliver_with_retry(wh["url"], generic_payload, key))
            _pending_tasks.add(task)
            task.add_done_callback(_pending_tasks.discard)

        for integ in integrations_snapshot:
            if event_type not in integ.get("events", ["alert.fired", "alert.resolved"]):
                continue
            if integ["type"] == "slack":
                payload = format_slack(alert, event_type, integ)
            elif integ["type"] == "discord":
                payload = format_discord(alert, event_type, integ)
            else:
                continue
            key = (integ["type"], integ["webhook_url"], alert_id, event_type)
            task = asyncio.create_task(deliver_with_retry(integ["webhook_url"], payload, key))
            _pending_tasks.add(task)
            task.add_done_callback(_pending_tasks.discard)
