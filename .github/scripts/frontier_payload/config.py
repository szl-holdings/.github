# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import dataclasses
import re

SCHEMA = "szl.frontier-payload-convergence/v1"
PAYLOAD_SHA256 = "55c29e76dede81ac61f51543696ec62bd05bdff6a0db829d91e0ebe32807b770"
GITHUB_API = "https://api.github.com"
HF_API = "https://huggingface.co/api"
USER_AGENT = "SZL-Frontier-Payload-Convergence/1.0"
MAX_BYTES = 2_000_000

GITHUB_TOKEN_NAMES = (
    "SZL_ORG_TOKEN", "SZL_ORG_ADMIN_TOKEN", "ORG_ADMIN_TOKEN",
    "SZL_GITHUB_TOKEN", "GH_PAT", "GH_TOKEN", "GITHUB_TOKEN",
)
HF_TOKEN_NAMES = (
    "HF_TOKEN", "HF_ORG_TOKEN", "HF_ORG_TOKEN1", "HF_WRITE_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
)
TOKEN_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"hf_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{12,})",
    re.IGNORECASE,
)
SHA40_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

VESSELS_CARD_URL = (
    "https://raw.githubusercontent.com/szl-holdings/killinchu/"
    "main/docs/hf-cards/SZLHOLDINGS-vessels.README.md"
)
VESSELS_SPACE = "SZLHOLDINGS/vessels"
PRIVATE_SPACES = (
    "hatun-mcp", "immune", "szl-model-inference-lab", "yarqa", "anatomy",
)

REPOSITORY_METADATA = {
    "szl-holdings/david-leads": {
        "description": (
            "Canonical public investor and lead-qualification surface; "
            "evidence-labelled company, product, market, diligence, and "
            "contact dossiers generated from live/public source inventories."
        ),
    },
    "szl-holdings/szl-atelier": {
        "description": (
            "Canonical SZL visual-asset and image-rendering studio; "
            "generated-media workflows, model adapters, and provenance-aware "
            "creative tooling."
        ),
        "archived": False,
    },
}

WORKFLOW_CONTROLS = (
    {
        "name": "organization-codeql-baseline",
        "repository": "szl-holdings/.github",
        "workflow": "org-code-scanning-baseline.yml",
        "inputs": {"apply": "true"},
        "precondition": None,
    },
    {
        "name": "canonical-a11oy-space-publish",
        "repository": "szl-holdings/a11oy",
        "workflow": "hf-sync.yml",
        "inputs": {},
        "precondition": "a11oy-alias-source",
    },
    {
        "name": "cloudflare-product-edge-production",
        "repository": "szl-holdings/a11oy",
        "workflow": "repair-cloudflare-product-edge-production.yml",
        "inputs": {"dry_run": "false"},
        "precondition": "a11oy-alias-source",
    },
    {
        "name": "nemo-v3-status-refresh",
        "repository": "szl-holdings/szl-gpu-bridge",
        "workflow": "nemo-v3-attempt-status.yml",
        "inputs": {},
        "precondition": None,
    },
)


@dataclasses.dataclass(frozen=True)
class ProbeContract:
    name: str
    url: str
    required_literals: tuple[str, ...] = ()
    json_contract: str | None = None
    critical: bool = True


PROBES = (
    ProbeContract("article-12-product", "https://a-11-oy.com/eu-ai-act", ("Article 12",)),
    ProbeContract("article-12-space", "https://szlholdings-a11oy.hf.space/eu-ai-act", ("Article 12",)),
    ProbeContract("a11oy-space-livez", "https://szlholdings-a11oy.hf.space/api/livez", json_contract="livez"),
    ProbeContract("a11oy-space-build-info", "https://szlholdings-a11oy.hf.space/api/build-info", json_contract="build-info"),
    ProbeContract("killinchu-maritime", "https://szlholdings-killinchu.hf.space/", ("Maritime",)),
    ProbeContract("proof-registry", "https://a11oy.net/", ("record",)),
    ProbeContract("product-spectral-alias", "https://a-11-oy.com/spectral", ("A11oy Holographic Operations",)),
    ProbeContract("product-controller-alias", "https://a-11-oy.com/controller", json_contract="controller"),
    ProbeContract("gdw-health", "https://gdw.a-11-oy.com/healthz", critical=False),
)


class FrontierError(RuntimeError):
    """Bounded provider, validation, or public-proof failure."""
