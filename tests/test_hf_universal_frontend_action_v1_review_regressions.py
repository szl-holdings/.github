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


def test_static_audits_declarative_shadow_roots_inside_noscript() -> None:
    with pytest.raises(
        CHECKER.ContractError,
        match="declarative shadow root template",
    ):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                body_contents=(
                    "<noscript><div><template shadowrootmode=\"open\">"
                    "<style>:host { overflow-x: auto !important; }</style>"
                    "</template></div></noscript>"
                )
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize(
    "noscript_contents",
    [
        "<style>html { overflow-x: auto !important; }</style>",
        '<link rel="stylesheet" href="./override.css">',
    ],
    ids=["style-element", "stylesheet-link"],
)
def test_static_audits_author_styles_inside_noscript(
    noscript_contents: str,
) -> None:
    with pytest.raises(CHECKER.ContractError, match="author styles"):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                body_contents=f"<noscript>{noscript_contents}</noscript>"
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )


def test_static_leaves_direct_noscript_shadow_template_inert() -> None:
    CHECKER.validate_framework_binding(
        "static",
        _static_document(
            body_contents=(
                "<noscript><template shadowrootmode=\"open\">"
                "<style>:host { overflow-x: auto !important; }</style>"
                "</template></noscript>"
            )
        ),
        app_file="index.html",
        css_file="assets/universal.css",
    )


def test_static_leaves_invalid_mode_shadow_template_inert() -> None:
    CHECKER.validate_framework_binding(
        "static",
        _static_document(
            body_contents=(
                "<div><template shadowrootmode=\"invalid\">"
                "<style>:host { overflow-x: auto !important; }</style>"
                "</template></div>"
            )
        ),
        app_file="index.html",
        css_file="assets/universal.css",
    )


def test_static_rejects_custom_element_declarative_shadow_root() -> None:
    with pytest.raises(
        CHECKER.ContractError,
        match="declarative shadow root template",
    ):
        CHECKER.validate_framework_binding(
            "static",
            _static_document(
                body_contents=(
                    "<szl-host><template shadowrootmode=\"open\">"
                    "<style>:host { overflow-x: auto !important; }</style>"
                    "</template></szl-host>"
                )
            ),
            app_file="index.html",
            css_file="assets/universal.css",
        )

@pytest.mark.parametrize(
    "override_rule",
    [
        "* { overflow-inline: auto !important; }",
        "* { writing-mode: vertical-rl; overflow-block: auto !important; }",
        r"* { overflow\2d inline: auto !important; }",
    ],
    ids=[
        "inline-default-writing-mode",
        "block-vertical-writing-mode",
        "escaped-inline-property",
    ],
)
def test_logical_overflow_cannot_override_physical_control(
    override_rule: str,
) -> None:
    css = """
:root { --szl-touch-target: 44px; }
* { overflow-wrap: anywhere; overflow-x: clip; }
@media (max-width: 560px) {
  body { padding-inline: 0.5rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; }
}
"""
    with pytest.raises(
        CHECKER.ContractError,
        match="logical overflow properties",
    ):
        CHECKER.validate_css(css + "\n" + override_rule + "\n")


@pytest.mark.parametrize(
    "app_text",
    [
        """<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width">
  <noscript>
    <link
      rel="stylesheet"
      href="./assets/universal.css"
      data-szl-universal-frontend="v1"
    >
  </noscript>
</head>
<body></body>
</html>
""",
        """<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width">
</head>
<body>
  <noscript>
    <link
      rel="stylesheet"
      href="./assets/universal.css"
      data-szl-universal-frontend="v1"
    >
  </noscript>
</body>
</html>
""",
    ],
    ids=["head-noscript", "body-noscript"],
)
def test_static_does_not_bind_managed_stylesheet_inside_noscript(
    app_text: str,
) -> None:
    with pytest.raises(
        CHECKER.ContractError,
        match="stylesheet <link>",
    ):
        CHECKER.validate_framework_binding(
            "static",
            app_text,
            app_file="index.html",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize(
    ("framework", "framework_import", "binding", "expected_error"),
    [
        (
            "streamlit",
            "import streamlit as ui",
            'ui.markdown(f"<style>{css}</style>", unsafe_allow_html=True)',
            "Streamlit universal CSS binding is absent",
        ),
        (
            "gradio",
            "import gradio as ui",
            "demo = ui.Blocks(css=css)",
            "Gradio universal CSS binding is absent",
        ),
    ],
)
def test_local_function_call_before_binding_fails_closed(
    framework: str,
    framework_import: str,
    binding: str,
    expected_error: str,
) -> None:
    app_text = f"""\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
{framework_import}

css = Path("assets/universal.css").read_text(encoding="utf-8")

def stop():
    raise RuntimeError("stop")

stop()
{binding}
"""

    with pytest.raises(CHECKER.ContractError, match=expected_error):
        CHECKER.validate_framework_binding(
            framework,
            app_text,
            app_file="app.py",
            css_file="assets/universal.css",
        )


def test_uncalled_local_function_does_not_block_streamlit_binding() -> None:
    app_text = """\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
import streamlit as st

css = Path("assets/universal.css").read_text(encoding="utf-8")

def stop():
    raise RuntimeError("stop")

st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
"""

    CHECKER.validate_framework_binding(
        "streamlit",
        app_text,
        app_file="app.py",
        css_file="assets/universal.css",
    )


def test_local_function_call_after_streamlit_binding_preserves_binding() -> None:
    app_text = """\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
import streamlit as st

css = Path("assets/universal.css").read_text(encoding="utf-8")

def stop():
    raise RuntimeError("stop")

st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
stop()
"""

    CHECKER.validate_framework_binding(
        "streamlit",
        app_text,
        app_file="app.py",
        css_file="assets/universal.css",
    )

@pytest.mark.parametrize(
    "keyframe_block",
    [
        """
@keyframes szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        """
@KeYfRaMeS szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        """
@-webkit-keyframes szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        """
@-moz-keyframes szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        r"""
@\6b eyframes szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        r"""
@-\77 ebkit-keyframes szl-overflow-bypass {
  from { overflow-x: clip; }
  to { overflow-x: auto; }
}
""",
        """
@media (max-width: 560px) {
  @keyframes szl-overflow-bypass {
    from { overflow-x: clip; }
    to { overflow-x: auto; }
  }
}
""",
    ],
    ids=[
        "standard",
        "mixed-case",
        "webkit-prefixed",
        "other-vendor-prefixed",
        "escaped-standard-at-keyword",
        "escaped-webkit-at-keyword",
        "nested-in-recognized-media",
    ],
)
def test_keyframe_blocks_fail_closed(keyframe_block: str) -> None:
    valid_css = """
:root { --szl-touch-target: 44px; }
* { overflow-wrap: anywhere; overflow-x: clip; }
@media (max-width: 560px) {
  body { padding-inline: 0.5rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; }
}
"""
    activation = """
html {
  animation-name: szl-overflow-bypass;
  animation-duration: 1s;
  -webkit-animation-name: szl-overflow-bypass;
  -webkit-animation-duration: 1s;
}
"""

    with pytest.raises(
        CHECKER.ContractError,
        match=r"unsupported (?:conditional or )?at-rule block",
    ):
        CHECKER.validate_css(valid_css + keyframe_block + activation)


@pytest.mark.parametrize(
    ("framework", "framework_import", "binding", "expected_error"),
    [
        (
            "streamlit",
            "import streamlit as ui",
            'ui.markdown(f"<style>{css}</style>", unsafe_allow_html=True)',
            "Streamlit universal CSS binding is absent",
        ),
        (
            "gradio",
            "import gradio as ui",
            "demo = ui.Blocks(css=css)",
            "Gradio universal CSS binding is absent",
        ),
    ],
)
@pytest.mark.parametrize(
    "definition",
    [
        """@explode()
def helper():
    pass""",
        """def helper(value=explode()):
    pass""",
        """def helper(*, value=explode()):
    pass""",
        """def helper(value: explode()):
    pass""",
        """def helper() -> explode():
    pass""",
        """@explode()
async def helper():
    pass""",
        """async def helper(value=explode()):
    pass""",
        """async def helper(*, value=explode()):
    pass""",
        """async def helper(value: explode()):
    pass""",
        """async def helper() -> explode():
    pass""",
        """class Helper:
    raise RuntimeError("stop")""",
        "helper = lambda value=explode(): value",
        "helper = (lambda value=explode(): value,)",
        "helper = [lambda value=explode(): value]",
        "helper = {'value': lambda value=explode(): value}",
        "helper = (lambda value=explode(): value) if choose else None",
        "helper = (nested := (lambda value=explode(): value))",
        "helper = (value for value in (lambda value=explode(): value,))",
        "helper = ((lambda: explode())(),)",
        "helper = ((nested := (lambda: explode()))(),)",
        """if True:
    (lambda value=explode(): value)""",
        """if True:
    (lambda: explode())()""",
        "helper = (lambda value=explode(): value) if True else None",
        "helper = True and (lambda value=explode(): value)",
        "helper = False or (lambda value=explode(): value)",
        """async def helper(value):
    return value
pending = helper(lambda value=explode(): value)""",
    ],
    ids=[
        "sync-decorator",
        "sync-positional-default",
        "sync-keyword-default",
        "sync-parameter-annotation",
        "sync-return-annotation",
        "async-decorator",
        "async-positional-default",
        "async-keyword-default",
        "async-parameter-annotation",
        "async-return-annotation",
        "class-body",
        "lambda-default",
        "tuple-lambda-default",
        "list-lambda-default",
        "dict-lambda-default",
        "conditional-lambda-default",
        "named-expression-lambda-default",
        "generator-outer-iter-lambda-default",
        "tuple-direct-lambda-call",
        "named-expression-direct-lambda-call",
        "branch-lambda-default-expression",
        "branch-direct-lambda-call",
        "taken-conditional-lambda-default",
        "true-and-lambda-default",
        "false-or-lambda-default",
        "async-call-eager-argument",
    ],
)
def test_definition_time_execution_before_binding_fails_closed(
    framework: str,
    framework_import: str,
    binding: str,
    expected_error: str,
    definition: str,
) -> None:
    app_text = f"""\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
{framework_import}

css = Path("assets/universal.css").read_text(encoding="utf-8")

{definition}

{binding}
"""

    with pytest.raises(CHECKER.ContractError, match=expected_error):
        CHECKER.validate_framework_binding(
            framework,
            app_text,
            app_file="app.py",
            css_file="assets/universal.css",
        )


@pytest.mark.parametrize(
    ("framework", "framework_import", "binding"),
    [
        (
            "streamlit",
            "import streamlit as ui",
            'ui.markdown(f"<style>{css}</style>", unsafe_allow_html=True)',
        ),
        (
            "gradio",
            "import gradio as ui",
            "demo = ui.Blocks(css=css)",
        ),
    ],
)
@pytest.mark.parametrize(
    "definition",
    [
        "helper = (lambda: explode(),)",
        "helper = ((lambda value=explode(): value) for _ in ())",
        """if True:
    (lambda: explode())""",
        """if False:
    (lambda value=explode(): value)""",
        "helper = (lambda value=explode(): value) if False else None",
        "helper = False and (lambda value=explode(): value)",
        "helper = True or (lambda value=explode(): value)",
        """async def helper():
    raise RuntimeError("not invoked")
pending = helper()""",
    ],
    ids=[
        "tuple-lazy-lambda-body",
        "lazy-generator-element-default",
        "branch-lazy-lambda-body",
        "untaken-branch-lambda-default",
        "untaken-conditional-lambda-default",
        "false-and-lambda-default",
        "true-or-lambda-default",
        "plain-async-coroutine-creation",
    ],
)
def test_lazy_nested_lambda_execution_before_binding_is_inert(
    framework: str,
    framework_import: str,
    binding: str,
    definition: str,
) -> None:
    app_text = f"""\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
{framework_import}

css = Path("assets/universal.css").read_text(encoding="utf-8")

{definition}

{binding}
"""

    CHECKER.validate_framework_binding(
        framework,
        app_text,
        app_file="app.py",
        css_file="assets/universal.css",
    )


def test_plain_async_definition_before_binding_is_inert() -> None:
    app_text = """\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
import streamlit as st

css = Path("assets/universal.css").read_text(encoding="utf-8")

async def helper():
    raise RuntimeError("not invoked")

st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
"""

    CHECKER.validate_framework_binding(
        "streamlit",
        app_text,
        app_file="app.py",
        css_file="assets/universal.css",
    )


def test_lazy_generic_bound_before_binding_is_inert() -> None:
    app_text = """\
# SZL_HF_UNIVERSAL_FRONTEND_V1
from pathlib import Path
import streamlit as st

css = Path("assets/universal.css").read_text(encoding="utf-8")

def helper[T: explode()]():
    pass

st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
"""

    CHECKER.validate_framework_binding(
        "streamlit",
        app_text,
        app_file="app.py",
        css_file="assets/universal.css",
    )
