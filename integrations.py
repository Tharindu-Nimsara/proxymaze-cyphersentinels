from state import now_epoch


def format_slack(alert: dict, event_type: str, integ: dict) -> dict:
    is_fired = event_type == "alert.fired"
    color = "#FF4136" if is_fired else "#2ECC40"

    fired_at = alert.get("fired_at", "")
    resolved_at = alert.get("resolved_at", "")
    failed_ids = alert.get("failed_proxy_ids", [])
    failed_ids_str = ", ".join(failed_ids) if failed_ids else "(none)"
    rate_pct = f"{alert['failure_rate'] * 100:.1f}%"
    threshold_pct = f"{alert['threshold'] * 100:.1f}%"

    text = (
        f"Proxy pool alert FIRED — failure rate {rate_pct}"
        if is_fired
        else f"Proxy pool alert RESOLVED — alert {alert['alert_id']}"
    )

    header_text = "Proxy Pool Alert FIRED" if is_fired else "Proxy Pool Alert RESOLVED"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": header_text},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Alert ID:*\n{alert['alert_id']}"},
                {"type": "mrkdwn", "text": f"*Failure Rate:*\n{rate_pct}"},
                {"type": "mrkdwn", "text": f"*Failed Proxies:*\n{alert.get('failed_proxies', 0)}"},
                {"type": "mrkdwn", "text": f"*Threshold:*\n{threshold_pct}"},
                {"type": "mrkdwn", "text": f"*Failed IDs:*\n{failed_ids_str}"},
                {"type": "mrkdwn", "text": f"*Fired At:*\n{fired_at}"},
            ],
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": "ProxyMaze Watchtower"}],
        },
    ]

    return {
        "username": integ.get("username") or "ProxyWatch",
        "text": text,
        "blocks": blocks,
        "attachments": [
            {
                "color": color,
                "fields": [
                    {"title": "Alert ID", "value": alert["alert_id"], "short": True},
                    {"title": "Failure Rate", "value": rate_pct, "short": True},
                    {"title": "Failed Proxies", "value": str(alert.get("failed_proxies", 0)), "short": True},
                    {"title": "Threshold", "value": threshold_pct, "short": True},
                    {"title": "Failed IDs", "value": failed_ids_str, "short": False},
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
    failed_ids_str = ", ".join(failed_ids) if failed_ids else "(none)"
    rate_pct = f"{alert['failure_rate'] * 100:.1f}%"
    threshold_pct = f"{alert['threshold'] * 100:.1f}%"
    title = "Proxy Pool Alert FIRED" if is_fired else "Proxy Pool Alert RESOLVED"
    description = (
        f"Failure rate {rate_pct} exceeded threshold {threshold_pct}"
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
                    {"name": "Failure Rate", "value": rate_pct, "inline": True},
                    {"name": "Failed Proxies", "value": str(alert.get("failed_proxies", 0)), "inline": True},
                    {"name": "Threshold", "value": threshold_pct, "inline": True},
                    {"name": "Failed IDs", "value": failed_ids_str, "inline": False},
                ],
                "footer": {"text": "ProxyMaze Watchtower"},
            }
        ],
    }
