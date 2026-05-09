from state import now_epoch


def format_slack(alert: dict, event_type: str, integ: dict) -> dict:
    is_fired = event_type == "alert.fired"
    color = "#FF4136" if is_fired else "#2ECC40"

    fired_at = alert.get("fired_at", "")
    failed_ids = alert.get("failed_proxy_ids", [])

    text = (
        f"Proxy pool alert FIRED — failure rate {alert['failure_rate']:.2%}"
        if is_fired
        else f"Proxy pool alert RESOLVED — alert {alert['alert_id']}"
    )

    return {
        "username": integ.get("username") or "ProxyWatch",
        "text": text,
        "attachments": [
            {
                "color": color,
                "fields": [
                    {"title": "Alert ID", "value": alert["alert_id"], "short": True},
                    {"title": "Failure Rate", "value": f"{alert['failure_rate']:.2%}", "short": True},
                    {"title": "Failed Proxies", "value": str(alert.get("failed_proxies", 0)), "short": True},
                    {"title": "Threshold", "value": f"{alert['threshold']:.2%}", "short": True},
                    {"title": "Failed IDs", "value": ", ".join(failed_ids) if failed_ids else "(none)", "short": False},
                    {"title": "Fired At", "value": fired_at, "short": True},
                ],
                "footer": "ProxyMaze Watchtower",
                "ts": now_epoch(),
            }
        ],
    }


def format_discord(alert: dict, event_type: str, integ: dict) -> dict:
    is_fired = event_type == "alert.fired"
    color = 0xFF4136 if is_fired else 0x2ECC40

    failed_ids = alert.get("failed_proxy_ids", [])
    title = "Proxy Pool Alert FIRED" if is_fired else "Proxy Pool Alert RESOLVED"
    description = (
        f"Failure rate {alert['failure_rate']:.2%} exceeded threshold {alert['threshold']:.2%}"
        if is_fired
        else f"Alert {alert['alert_id']} has been resolved at {alert.get('resolved_at', '')}"
    )

    return {
        "username": integ.get("username") or "ProxyWatch",
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "fields": [
                    {"name": "Alert ID", "value": alert["alert_id"], "inline": True},
                    {"name": "Failure Rate", "value": f"{alert['failure_rate']:.2%}", "inline": True},
                    {"name": "Failed Proxies", "value": str(alert.get("failed_proxies", 0)), "inline": True},
                    {"name": "Threshold", "value": f"{alert['threshold']:.2%}", "inline": True},
                    {"name": "Failed IDs", "value": ", ".join(failed_ids) if failed_ids else "(none)", "inline": False},
                ],
                "footer": {"text": "ProxyMaze Watchtower"},
            }
        ],
    }
