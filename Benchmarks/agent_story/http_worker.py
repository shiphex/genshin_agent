"""One HTTP operation in a killable child; stdin config, stdout response, no agent logic."""
import json
import os
import sys
from urllib.request import Request, urlopen


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    request = json.load(sys.stdin)
    config, payload = request["config"], request["payload"]
    headers = {"Content-Type": "application/json"}
    env = config.get("api_key_env")
    if env:
        value = os.environ.get(env)
        if not value:
            raise ValueError("missing API key environment variable")
        headers["Authorization"] = "Bearer " + value
    operation = Request(config["base_url"].rstrip("/") + "/" + request["endpoint"],
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8") if payload is not None else None,
        headers=headers)
    with urlopen(operation, timeout=request["timeout"]) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024:
        raise ValueError("HTTP response exceeds 16 MiB")
    result = json.loads(data.decode("utf-8"))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print headers, credentials, response bodies or request URLs on errors.
        print(json.dumps({"exception_type": type(exc).__name__}))
        raise SystemExit(2)
