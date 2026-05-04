"""Docker healthcheck entrypoint: verifies the bot heartbeat is fresh."""

from __future__ import annotations

import sys

from utils.heartbeat import heartbeat_path, heartbeat_stale_after, is_heartbeat_fresh


def main() -> int:
    target = heartbeat_path()
    threshold = heartbeat_stale_after()
    if is_heartbeat_fresh(path=target, stale_after=threshold):
        return 0
    sys.stderr.write(
        f"heartbeat at {target} is missing or older than {threshold:.0f}s\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
