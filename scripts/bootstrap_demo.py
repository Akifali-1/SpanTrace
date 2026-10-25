from __future__ import annotations

import argparse
import json
import urllib.request


def post(url: str, body: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a local AgentScope demo project and one API key")
    parser.add_argument("--api-url", default="http://localhost:8070")
    parser.add_argument("--name", default="Travel Booking Demo")
    args = parser.parse_args()
    result = post(f"{args.api_url.rstrip('/')}/v1/projects", {"name": args.name})
    print(json.dumps(result, indent=2))
    print("\nExport these values in your shell (the raw key is shown only in this response):")
    print(f"export AGENTSCOPE_PROJECT_ID='{result['project']['id']}'")
    print(f"export AGENTSCOPE_API_KEY='{result['api_key']}'")
