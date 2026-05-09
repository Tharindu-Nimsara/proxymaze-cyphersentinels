import uuid
from typing import List
from state import state, now_iso

THRESHOLD = 0.20


def compute_pool_stats():
    total = len(state.proxies)
    if total == 0:
        return 0, 0, 0, 0.0, []

    up = sum(1 for p in state.proxies.values() if p["status"] == "up")
    down = sum(1 for p in state.proxies.values() if p["status"] == "down")
    down_ids = sorted([p["id"] for p in state.proxies.values() if p["status"] == "down"])
    failure_rate = round(down / total, 4)
    return total, up, down, failure_rate, down_ids


def evaluate_alert_state() -> List[dict]:
    transitions = []
    total, up, down, failure_rate, down_ids = compute_pool_stats()

    if total == 0:
        return transitions

    breach = failure_rate >= THRESHOLD

    if breach and state.active_alert is None:
        alert = {
            "alert_id": f"alert-{uuid.uuid4().hex[:12]}",
            "status": "active",
            "failure_rate": failure_rate,
            "total_proxies": total,
            "failed_proxies": down,
            "failed_proxy_ids": down_ids,
            "threshold": THRESHOLD,
            "fired_at": now_iso(),
            "resolved_at": None,
            "message": "Proxy pool failure rate exceeded threshold",
        }
        state.alerts.append(alert)
        state.active_alert = alert
        transitions.append({"event": "alert.fired", "alert": alert})

    elif breach and state.active_alert is not None:
        state.active_alert["failure_rate"] = failure_rate
        state.active_alert["total_proxies"] = total
        state.active_alert["failed_proxies"] = down
        state.active_alert["failed_proxy_ids"] = down_ids

    elif not breach and state.active_alert is not None:
        alert = state.active_alert
        alert["status"] = "resolved"
        alert["resolved_at"] = now_iso()
        alert["failed_proxy_ids"] = down_ids
        alert["failed_proxies"] = down
        alert["failure_rate"] = failure_rate
        alert["total_proxies"] = total
        state.active_alert = None
        transitions.append({"event": "alert.resolved", "alert": alert})

    return transitions
