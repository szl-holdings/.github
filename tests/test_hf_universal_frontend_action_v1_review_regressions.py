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
    body_contents: str = "",
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
<body{body_attributes}>{body_contents}</body>
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
        (
            "<svg><foreignObject><div "
            'style="width:200vw"></div></foreignObject></svg>',
            "",
        ),
        (
            '<math><annotation-xml encoding=" text/html "><template>'
            '<mrow style="width:200vw"></mrow>'
            "</template></annotation-xml></math>",
            "",
        ),
        (
            "<math><mtext><mglyph><template>"
            '<mrow style="width:200vw"></mrow>'
            "</template></mglyph></mtext></math>",
            "",
        ),
        (
            "<svg><math><mtext><template>"
            '<g style="width:200vw"></g>'
            "</template></mtext></math></svg>",
            "",
        ),
        (
            "<math><annotation-xml><svg><mtext><template>"
            '<svg style="width:200vw"></svg>'
            "</template></mtext></svg></annotation-xml></math>",
            "",
        ),
        (
            "<math><div><svg><mtext><template>"
            '<svg style="width:200vw"></svg>'
            "</template></mtext></svg></div></math>",
            "",
        ),
        (
            '<svg><font color="red"><svg><mtext><template>'
            '<svg style="width:200vw"></svg>'
            "</template></mtext></svg></font></svg>",
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
        "foreign-object-style-attribute",
        "padded-annotation-encoding",
        "mathml-glyph-exception",
        "svg-nested-math-tag",
        "annotation-xml-svg-transition",
        "foreign-div-breakout",
        "foreign-font-breakout",
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


@pytest.mark.parametrize(
    "foreign_markup",
    [
        (
            "<svg><foreignObject><template><style>"
            "html { width: 200vw; }"
            "</style></template></foreignObject></svg>"
        ),
        (
            "<svg><foreignObject><div><template><style>"
            "html { width: 200vw; }"
            "</style></template></div></foreignObject></svg>"
        ),
        (
            "<svg><desc><template><style>"
            "html { width: 200vw; }"
            "</style></template></desc></svg>"
        ),
        (
            "<math><mtext><template><style>"
            "html { width: 200vw; }"
            "</style></template></mtext></math>"
        ),
        (
            '<math><annotation-xml encoding="text/html"><template><style>'
            "html { width: 200vw; }"
            "</style></template></annotation-xml></math>"
        ),
    ],
    ids=[
        "svg-foreign-object",
        "svg-foreign-object-html-descendant",
        "svg-description",
        "mathml-text",
        "mathml-annotation",
    ],
)
def test_static_ignores_inert_templates_at_foreign_html_integration_points(
    foreign_markup: str,
) -> None:
    CHECKER.validate_framework_binding(
        "static",
        _static_document(extra_head=foreign_markup),
        app_file="index.html",
        css_file="assets/universal.css",
    )


def test_static_does_not_treat_raw_svg_template_as_html_inert() -> None:
    with pytest.raises(CHECKER.ContractError, match="author styles"):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                extra_head=(
                    "<svg><template><style>"
                    "html { width: 200vw; }"
                    "</style></template></svg>"
                )
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize(
    "foreign_markup",
    [
        (
            "<math><mtext><p><math><div></div><mglyph><template>"
            '<mrow style="width:200vw"></mrow>'
            "</template></mglyph></p></mtext></math>"
        ),
        (
            "<math><mtext><p><math></p><mglyph><template>"
            '<mrow style="width:200vw"></mrow>'
            "</template></mglyph></p></mtext></math>"
        ),
    ],
    ids=["breakout-start-reprocessing", "breakout-end-reprocessing"],
)
def test_static_rejects_foreign_content_breakout_parse_errors(
    foreign_markup: str,
) -> None:
    with pytest.raises(
        CHECKER.ContractError,
        match="foreign-content breakout parse error",
    ):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(extra_head=foreign_markup),
            app_file="index.html",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize("mode", ["open", "closed"])
def test_static_rejects_declarative_shadow_root_templates(mode: str) -> None:
    with pytest.raises(
        CHECKER.ContractError,
        match="declarative shadow root template",
    ):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                body_contents=(
                    "<div><template "
                    f'shadowrootmode="{mode}">'
                    "<style>:host { overflow-x: auto !important; }</style>"
                    "</template></div>"
                )
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )
