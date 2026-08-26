from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHECK_PATH = ROOT / "actions" / "hf-universal-frontend-v1" / "check.py"
SPEC = importlib.util.spec_from_file_location(
    "hf_universal_frontend_review_checker",
    CHECK_PATH,
)
assert SPEC is not None and SPEC.loader is not None
CHECKER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CHECKER
SPEC.loader.exec_module(CHECKER)


def _static_document(
    *,
    viewport: str = "width=device-width, initial-scale=1",
    extra_head: str = "",
    body_attributes: str = "",
    integrity: str = "",
) -> str:
    integrity_attribute = f' integrity="{integrity}"' if integrity else ""
    return f"""<!doctype html>
<html>
<head>
  <meta name="viewport" content="{viewport}">
  <link
    rel="stylesheet"
    href="./assets/universal.css"
    data-szl-universal-frontend="v1"{integrity_attribute}
  >
  {extra_head}
</head>
<body{body_attributes}></body>
</html>
"""


@pytest.mark.parametrize(
    ("extra_head", "body_attributes"),
    [
        (
            "<style>html, body { overflow-x: auto !important; }</style>",
            "",
        ),
        ('<link rel="stylesheet" href="./override.css">', ""),
        ("", ' style="overflow-x: auto !important"'),
        (
            '<svg style="overflow-x:auto!important;width:200vw"></svg>',
            "",
        ),
        (
            "<svg><style>svg { width: 200vw !important; }</style></svg>",
            "",
        ),
        (
            '<math><mrow style="width:200vw"></mrow></math>',
            "",
        ),
    ],
    ids=[
        "style-element",
        "second-stylesheet",
        "style-attribute",
        "svg-style-attribute",
        "svg-style-element",
        "mathml-style-attribute",
    ],
)
def test_static_rejects_unaudited_author_styles(
    extra_head: str,
    body_attributes: str,
) -> None:
    with pytest.raises(CHECKER.ContractError, match="author styles"):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                extra_head=extra_head,
                body_attributes=body_attributes,
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )


def test_static_rejects_integrity_on_managed_stylesheet() -> None:
    with pytest.raises(CHECKER.ContractError, match="integrity"):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                integrity="sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize(
    "viewport",
    [
        "width=1024",
        "width=device-width, width=1024",
    ],
    ids=["fixed-width", "duplicate-width"],
)
def test_static_requires_unambiguous_device_width_viewport(viewport: str) -> None:
    with pytest.raises(CHECKER.ContractError, match="width=device-width"):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(viewport=viewport),
            app_file="index.html",
            css_file="assets/universal.css",
        )


def test_partial_conditional_does_not_guarantee_later_binding_reachability() -> None:
    tree = ast.parse(
        """
if runtime_condition:
    raise RuntimeError("stop")
"""
    )

    assert not CHECKER._statements_fall_through(tree.body)
