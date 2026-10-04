#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the reviewed inventory suites with no HF credentials or Python networking."""
from contextlib import ExitStack
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

SUITES = (
    "test_hf_official_estate_inventory",
    "test_hf_official_estate_inventory_compat",
    "test_hf_inventory_public_boundary",
    "test_hf_inventory_workflow_boundary",
    "test_hf_inventory_evidence",
)
HF_CREDENTIALS = ("HF_TOKEN", "HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HUGGING_FACE_HUB_TOKEN")


def deny_network(*_args, **_kwargs):
    raise RuntimeError("INVENTORY_CONTRACT_NETWORK_FORBIDDEN")


def main() -> int:
    if any(os.environ.get(name) for name in HF_CREDENTIALS):
        print("Inventory contracts require an environment without HF credentials.", file=sys.stderr)
        return 2
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    with ExitStack() as stack:
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.socket.sendto", "socket.create_connection", "socket.getaddrinfo"):
            stack.enter_context(patch(target, side_effect=deny_network))
        # Fail before loading the SDK or suites if the offline guard is absent.
        try:
            socket.create_connection(("inventory-network-must-be-blocked.invalid", 443), timeout=1)
        except RuntimeError as error:
            if str(error) != "INVENTORY_CONTRACT_NETWORK_FORBIDDEN":
                raise
        else:
            raise RuntimeError("INVENTORY_CONTRACT_NETWORK_GUARD_MISSING")
        suite = unittest.defaultTestLoader.loadTestsFromNames(SUITES)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
