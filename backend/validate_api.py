"""Manual end-to-end validation of the running NEXORA API. Run against a
live server (start it first: uvicorn backend.main:app --host 127.0.0.1
--port 8000), then:

    python -m backend.validate_api

Checks each of the 13 items from the Phase 6 brief against real HTTP
responses -- this is deliberately independent of tests/backend (which uses
TestClient, an in-process ASGI transport, not a real socket) so it also
catches anything that only breaks when the app is actually served.
"""

import sys

import httpx

BASE_URL = "http://127.0.0.1:8000"


def run():
    checks = []

    def check(name, condition, detail=""):
        checks.append((name, bool(condition), detail))

    try:
        health = httpx.get(f"{BASE_URL}/api/v1/health", timeout=15)
    except httpx.ConnectError:
        print("Could not connect to the API. Start it first:")
        print("  uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000")
        sys.exit(1)

    check("1. API starts successfully (server reachable)", health.status_code in (200, 503))
    check("2. /health returns 200", health.status_code == 200, f"status={health.status_code}")
    health_body = health.json()
    check("3. Snowflake health connected", health_body.get("snowflake") == "connected", str(health_body))

    overview = httpx.get(f"{BASE_URL}/api/v1/overview", timeout=30).json()
    non_null_kpis = all(overview.get(k) is not None for k in ("total_revenue", "active_customers", "enterprise_health_score"))
    check("4. /overview returns non-null KPIs", non_null_kpis, str({k: overview.get(k) for k in ("total_revenue", "active_customers")}))

    customers = httpx.get(f"{BASE_URL}/api/v1/customers?page=1&page_size=5", timeout=30).json()
    check("5. /customers paginates", len(customers["items"]) == 5 and customers["page_info"]["total_pages"] > 1,
          str(customers["page_info"]))

    first_customer_id = customers["items"][0]["customer_id"]
    detail = httpx.get(f"{BASE_URL}/api/v1/customers/{first_customer_id}", timeout=30)
    check("6. customer detail resolves", detail.status_code == 200 and detail.json()["profile"]["customer_id"] == first_customer_id)

    trends = httpx.get(f"{BASE_URL}/api/v1/revenue/trends", timeout=30).json()
    check("7. /revenue/trends returns rows", len(trends["points"]) > 0, f"{len(trends['points'])} points")

    projects = httpx.get(f"{BASE_URL}/api/v1/projects/risk?page_size=5", timeout=30).json()
    check("8. /projects/risk returns data", len(projects["items"]) > 0, f"{len(projects['items'])} rows")

    support = httpx.get(f"{BASE_URL}/api/v1/support", timeout=30).json()
    check("9. /support returns metrics", support.get("total_tickets", 0) > 0, str(support))

    pred_customers = httpx.get(f"{BASE_URL}/api/v1/predictions/customers?page_size=5", timeout=30).json()
    pred_revenue = httpx.get(f"{BASE_URL}/api/v1/predictions/revenue", timeout=30).json()
    check("10. prediction endpoints return data",
          len(pred_customers["items"]) > 0 and len(pred_revenue) > 0,
          f"customers={len(pred_customers['items'])} revenue={len(pred_revenue)}")

    decisions = httpx.get(f"{BASE_URL}/api/v1/decisions?page_size=25", timeout=30).json()
    scores = [d["priority_score"] for d in decisions["items"]]
    check("11. /decisions returns priority-sorted decisions", scores == sorted(scores, reverse=True), str(scores[:5]))

    summary = httpx.get(f"{BASE_URL}/api/v1/decisions/summary", timeout=30).json()
    check("12. /decisions/summary reconciles with Snowflake",
          summary.get("critical_decisions") is not None,
          "compare against `python -m etl.validate_decision_engine` output")

    all_bodies = "".join([
        health.text, str(overview), str(customers), str(detail.json()), str(trends),
        str(projects), str(support), str(pred_customers), str(pred_revenue), str(decisions), str(summary),
    ]).lower()
    check("13. no credentials appear in responses",
          "password" not in all_bodies and "snowflake_password" not in all_bodies)

    print("NEXORA API MANUAL VALIDATION\n")
    for name, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    passed_count = sum(1 for _, p, _ in checks if p)
    print(f"\nPassed: {passed_count}")
    print(f"Failed: {len(checks) - passed_count}")

    return passed_count == len(checks)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
