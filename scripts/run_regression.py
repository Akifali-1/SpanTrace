from __future__ import annotations

import argparse
import json
import urllib.request


def request(url: str, key: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "X-API-Key": key}, method=method)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create or execute a travel-booking regression case")
    parser.add_argument("action", choices=["create", "run"])
    parser.add_argument("--api-url", default="http://localhost:8070")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--trace-id")
    parser.add_argument("--case-id")
    parser.add_argument("--fixed", action="store_true")
    args = parser.parse_args()
    base = args.api_url.rstrip("/")
    if args.action == "create":
        if not args.trace_id:
            parser.error("--trace-id is required for create")
        result = request(f"{base}/v1/runs/{args.trace_id}/regression-case", args.api_key, "POST", {"name": "Travel approval invariant"})
    else:
        if not args.case_id:
            parser.error("--case-id is required for run")
        result = request(f"{base}/v1/regression-cases/{args.case_id}/run", args.api_key, "POST", {"fixed": args.fixed})
    print(json.dumps(result, indent=2))
