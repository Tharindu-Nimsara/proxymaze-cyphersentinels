from typing import Dict, List, Optional
from threading import Lock
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class State:
    def __init__(self):
        self.lock = Lock()

        self.config = {
            "check_interval_seconds": 15,
            "request_timeout_ms": 3000,
        }

        self.proxies: Dict[str, dict] = {}

        self.alerts: List[dict] = []
        self.active_alert: Optional[dict] = None

        self.webhooks: List[dict] = []
        self.integrations: List[dict] = []

        self.delivered: set = set()

        self.total_checks = 0
        self.webhook_deliveries = 0


state = State()
