"""
End-to-end scenario test.
Run mock_proxies.py on :9000 and main.py on :8000 first, then run this.
Tests the full lifecycle: load -> breach -> alert fire -> recover -> resolve -> re-breach.
"""
import time
import httpx

PROXYMAZE = "http://localhost:8000"
MOCK = "http://localhost:9000"


def step(msg):
    print(f"\n=== {msg} ===")


def main():
    # 1. Health check
    step("Health check")
    r = httpx.get(f"{PROXYMAZE}/health")
    print(r.status_code, r.json())
    assert r.status_code == 200 and r.json() == {"status": "ok"}

    # 2. Set fast config so the test doesn't take forever
    step("Configure fast checks")
    r = httpx.post(f"{PROXYMAZE}/config", json={
        "check_interval_seconds": 2,
        "request_timeout_ms": 1500,
    })
    print(r.status_code, r.json())

    # 3. Verify config readback
    step("Read config")
    r = httpx.get(f"{PROXYMAZE}/config")
    print(r.status_code, r.json())

    # 4. Load 10 proxies
    step("Load 10 proxies")
    proxies = [f"{MOCK}/proxy/px-{i}" for i in range(101, 111)]
    r = httpx.post(f"{PROXYMAZE}/proxies", json={
        "proxies": proxies,
        "replace": True,
        "extra_field": "should_be_ignored",  # test unknown-field tolerance
    })
    print(r.status_code, r.json())
    assert r.status_code == 201

    # 5. Wait for first check cycle
    step("Wait 5s for first check cycle")
    time.sleep(5)

    r = httpx.get(f"{PROXYMAZE}/proxies")
    print("Pool:", r.json())

    # 6. Kill 3 proxies (30% failure -> over threshold)
    step("Kill 3 proxies (30% failure rate)")
    for pid in ["px-101", "px-102", "px-103"]:
        httpx.post(f"{MOCK}/admin/kill/{pid}")

    time.sleep(5)

    # 7. Check alerts
    step("Should have 1 active alert")
    r = httpx.get(f"{PROXYMAZE}/alerts")
    print(r.json())
    assert any(a["status"] == "active" for a in r.json())

    r = httpx.get(f"{PROXYMAZE}/proxies")
    print("Pool after kill:", r.json())

    # 8. Heal them
    step("Heal proxies (recovery)")
    for pid in ["px-101", "px-102", "px-103"]:
        httpx.post(f"{MOCK}/admin/heal/{pid}")

    time.sleep(5)

    step("Alert should now be resolved")
    r = httpx.get(f"{PROXYMAZE}/alerts")
    print(r.json())
    assert all(a["status"] == "resolved" for a in r.json())

    # 9. Re-breach
    step("Re-breach: kill 4 proxies")
    for pid in ["px-104", "px-105", "px-106", "px-107"]:
        httpx.post(f"{MOCK}/admin/kill/{pid}")

    time.sleep(5)

    r = httpx.get(f"{PROXYMAZE}/alerts")
    print("Alerts (should be 2 total, 1 active):", r.json())
    assert len(r.json()) == 2
    active = [a for a in r.json() if a["status"] == "active"]
    resolved = [a for a in r.json() if a["status"] == "resolved"]
    assert len(active) == 1 and len(resolved) == 1
    assert active[0]["alert_id"] != resolved[0]["alert_id"], "new alert needs new id"

    # 10. Metrics
    step("Metrics")
    r = httpx.get(f"{PROXYMAZE}/metrics")
    print(r.json())

    print("\n✅ All scenarios passed.")


if __name__ == "__main__":
    main()
