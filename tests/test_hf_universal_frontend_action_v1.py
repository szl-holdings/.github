from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "actions" / "hf-universal-frontend-v1" / "check.py"
SPEC = importlib.util.spec_from_file_location("hf_frontend_action_v1", CHECK)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

CSS = """:root {
  --szl-touch-target: 44px;
}
* {
  overflow-wrap: anywhere;
  overflow-x: clip;
}
@media (max-width: 560px) {
  body { padding-inline: 0.5rem; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; }
}
"""


def _sha(path: Path) -> str:
    return MODULE.sha256(path)


def _fixture(root: Path, framework: str = "static") -> None:
    (root / "docs").mkdir(parents=True)
    if framework == "static":
        app = root / "index.html"
        app.write_text(
            '<html><head><meta name="viewport" content="width=device-width, initial-scale=1">'
            '<link rel="stylesheet" href="./szl-universal-frontend.css" data-szl-universal-frontend="v1">'
            "</head><body></body></html>",
            encoding="utf-8",
        )
        app_file = "index.html"
        sdk = "static"
    elif framework == "gradio":
        app = root / "app.py"
        app.write_text(
            "from pathlib import Path\n"
            "import gradio as gr\n\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text(encoding='utf-8')\n"
            "demo = gr.Blocks(css=_SZL_UNIVERSAL_CSS)\n",
            encoding="utf-8",
        )
        app_file = "app.py"
        sdk = "gradio"
    elif framework == "streamlit":
        app = root / "app.py"
        app.write_text(
            "from pathlib import Path\n"
            "import streamlit as st\n\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text(encoding='utf-8')\n"
            "st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n",
            encoding="utf-8",
        )
        app_file = "app.py"
        sdk = "streamlit"
    elif framework == "react":
        app = root / "main.tsx"
        app.write_text(
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            'import "./szl-universal-frontend.css";\n'
            "export const App = () => <main>ok</main>;\n",
            encoding="utf-8",
        )
        app_file = "main.tsx"
        sdk = "static"
    else:
        raise AssertionError(framework)
    css = root / "szl-universal-frontend.css"
    css.write_text(CSS, encoding="utf-8")
    (root / "README.md").write_text(
        "---\n"
        "title: Example\n"
        f"sdk: {sdk}\n"
        f"app_file: {app_file}\n"
        "short_description: Governed example\n"
        "fullWidth: true\n"
        "header: mini\n"
        "---\n"
        "# Example\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "szl.hf-universal-frontend/v1",
        "remote_mutation": False,
        "sdk": sdk,
        "framework": framework,
        "app_file": app_file,
        "css_file": "szl-universal-frontend.css",
        "entry_file": None,
        "contract": {
            "viewport_classes": [360, 390, 768, 1024, 1440],
            "minimum_touch_target_px": 44,
            "horizontal_overflow_allowed": False,
            "reduced_motion_required": True,
            "technical_identifier_wrapping_required": True,
        },
        "file_sha256": {
            "README.md": _sha(root / "README.md"),
            app_file: _sha(app),
            "szl-universal-frontend.css": _sha(css),
        },
    }
    (root / "docs" / "hf-universal-frontend-v1.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _manifest(root: Path) -> tuple[Path, dict[str, object]]:
    path = root / "docs" / "hf-universal-frontend-v1.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def test_static_contract_passes(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["status"] == "PASS"
    assert result["framework"] == "static"
    assert result["sdk"] == "static"
    assert result["remote_mutation"] is False


def test_gradio_contract_passes(tmp_path: Path) -> None:
    _fixture(tmp_path, "gradio")
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["framework"] == "gradio"
    assert result["sdk"] == "gradio"


def test_streamlit_contract_passes(tmp_path: Path) -> None:
    _fixture(tmp_path, "streamlit")
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["framework"] == "streamlit"
    assert result["sdk"] == "streamlit"


def test_react_contract_passes_with_live_stylesheet_import(tmp_path: Path) -> None:
    _fixture(tmp_path, "react")
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["framework"] == "react"
    assert result["sdk"] == "static"


def test_react_contract_allows_static_imports_before_marker(tmp_path: Path) -> None:
    _fixture(tmp_path, "react")
    app = tmp_path / "main.tsx"
    app.write_text(
        "import {\n"
        "  StrictMode,\n"
        '} from "react";\n'
        "// SZL_HF_UNIVERSAL_FRONTEND_V1\n"
        'import "./szl-universal-frontend.css";\n'
        "export const App = () => <StrictMode>ok</StrictMode>;\n",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["main.tsx"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["framework"] == "react"


def test_hash_drift_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "index.html").write_text("drift", encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="hash mismatch"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_partial_hash_manifest_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    del payload["file_sha256"]["index.html"]
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing managed paths: index.html"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    payload["app_file"] = "../outside.py"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="safe repository-relative path"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize("line_break", ["\n", "\r", "\r\n"])
def test_manifest_path_line_break_is_rejected(
    tmp_path: Path,
    line_break: str,
) -> None:
    _fixture(tmp_path)
    manifest_path = tmp_path / "docs" / "hf-universal-frontend-v1.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["app_file"] = f"index.html{line_break}css_file=unverified.css"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="may not contain CR or LF"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_managed_file_symlink_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    target = tmp_path / "index-target.html"
    app.rename(target)
    app.symlink_to(target.name)
    with pytest.raises(MODULE.ContractError, match="may not contain a symlink"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_missing_css_control_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(CSS.replace("overflow-x: clip;", ""), encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing required active tokens"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    "css_text",
    [
        f"/* {CSS} */",
        f"/* {CSS}",
        CSS.replace("overflow-wrap: anywhere", "overflow-/* inert */wrap: anywhere"),
        'body::before { content: "' + CSS.replace("\n", " ") + '"; }',
    ],
)
def test_inert_css_controls_are_rejected(
    tmp_path: Path,
    css_text: str,
) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(css_text, encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing required active tokens"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    "wrapper",
    [
        "@media not all {" + CSS + "}",
        "@unknown inert {" + CSS + "}",
    ],
)
def test_non_applying_css_rules_are_rejected(tmp_path: Path, wrapper: str) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(wrapper, encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing required active tokens"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize("selector", [":not(*)", "*, :not(", "h t m l"])
def test_impossible_css_selectors_cannot_satisfy_controls(
    tmp_path: Path,
    selector: str,
) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(
        f"{selector} {{\n"
        "  --szl-touch-target: 44px;\n"
        "  overflow-wrap: anywhere;\n"
        "  overflow-x: clip;\n"
        "}\n"
        "@media (max-width: 560px) {\n"
        f"  {selector} {{ padding-inline: 0.5rem; }}\n"
        "}\n"
        "@media (prefers-reduced-motion: reduce) {\n"
        f"  {selector} {{ animation-duration: 0.01ms !important; }}\n"
        "}\n",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing required active tokens"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_reduced_motion_media_requires_an_active_control(tmp_path: Path) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(
        CSS.replace("animation-duration: 0.01ms !important", "color: red"),
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="prefers-reduced-motion"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_sdk_framework_mismatch_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    payload["framework"] = "gradio"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="not compatible with framework"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_card_and_manifest_sdk_must_match(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    payload["sdk"] = "docker"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="diverges from manifest sdk"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    "stylesheet_markup",
    [
        '<link rel="stylesheet" href="./szl-universal-frontend.css">'
        + '<div data-szl-universal-frontend="v1"></div>',
        '<!-- <link rel="stylesheet" href="./szl-universal-frontend.css" '
        + 'data-szl-universal-frontend="v1"> -->',
        '<link rel="stylesheet" href="./other.css" '
        + 'data-szl-universal-frontend="v1">',
        '<template><link rel="stylesheet" href="./szl-universal-frontend.css" '
        + 'data-szl-universal-frontend="v1"></template>',
        '<link rel="stylesheet" href="./szl-universal-frontend.css" '
        + 'data-szl-universal-frontend="v1" disabled>',
    ],
)
def test_static_marker_must_bind_the_declared_stylesheet(
    tmp_path: Path,
    stylesheet_markup: str,
) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        f"{stylesheet_markup}</head><body></body></html>",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["index.html"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="stylesheet <link>"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize("container", ["svg", "math"])
def test_static_stylesheet_link_must_be_in_html_namespace(
    tmp_path: Path,
    container: str,
) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        f'<{container}><link rel="stylesheet" href="./szl-universal-frontend.css" '
        f'data-szl-universal-frontend="v1"></link></{container}>'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["index.html"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="stylesheet <link>"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    ("framework", "app_text", "message"),
    [
        (
            "gradio",
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n# _SZL_UNIVERSAL_CSS\n",
            "does not read the declared CSS",
        ),
        (
            "gradio",
            "from pathlib import Path\n"
            "import gradio as gr\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text()\n",
            "Gradio universal CSS binding is absent",
        ),
        (
            "gradio",
            "from pathlib import Path\n"
            "import gradio as gr\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text()\n"
            "_SZL_UNIVERSAL_CSS = ''\n"
            "demo = gr.Blocks(css=_SZL_UNIVERSAL_CSS)\n",
            "does not read the declared CSS",
        ),
        (
            "streamlit",
            "from pathlib import Path\n"
            "import streamlit as st\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text()\n"
            "# st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n",
            "Streamlit universal CSS binding is absent",
        ),
        (
            "streamlit",
            "from pathlib import Path\n"
            "import streamlit as st\n"
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text()\n"
            "st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>' if False else '', "
            "unsafe_allow_html=True)\n",
            "Streamlit universal CSS binding is absent",
        ),
    ],
)
def test_python_framework_must_apply_declared_css(
    tmp_path: Path,
    framework: str,
    app_text: str,
    message: str,
) -> None:
    _fixture(tmp_path, framework)
    app = tmp_path / "app.py"
    app.write_text(app_text, encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["app.py"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match=message):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    ("framework", "dead_binding", "message"),
    [
        (
            "gradio",
            "if False:\n    demo = gr.Blocks(css=_SZL_UNIVERSAL_CSS)\n",
            "Gradio universal CSS binding is absent",
        ),
        (
            "gradio",
            "def build():\n    return gr.Blocks(css=_SZL_UNIVERSAL_CSS)\n",
            "Gradio universal CSS binding is absent",
        ),
        (
            "streamlit",
            "if False:\n"
            + "    st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n",
            "Streamlit universal CSS binding is absent",
        ),
        (
            "streamlit",
            "def render():\n"
            + "    st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n",
            "Streamlit universal CSS binding is absent",
        ),
        (
            "gradio",
            "raise SystemExit\n"
            + "demo = gr.Blocks(css=_SZL_UNIVERSAL_CSS)\n",
            "Gradio universal CSS binding is absent",
        ),
        (
            "streamlit",
            "raise SystemExit\n"
            + "st.markdown(f'<style>{_SZL_UNIVERSAL_CSS}</style>', unsafe_allow_html=True)\n",
            "Streamlit universal CSS binding is absent",
        ),
    ],
)
def test_python_framework_binding_in_dead_code_is_rejected(
    tmp_path: Path,
    framework: str,
    dead_binding: str,
    message: str,
) -> None:
    _fixture(tmp_path, framework)
    module_name = "gradio as gr" if framework == "gradio" else "streamlit as st"
    app = tmp_path / "app.py"
    app.write_text(
        "from pathlib import Path\n"
        + f"import {module_name}\n"
        + "# SZL_HF_UNIVERSAL_FRONTEND_V1\n"
        + "_SZL_UNIVERSAL_CSS = Path('szl-universal-frontend.css').read_text()\n"
        + dead_binding,
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["app.py"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match=message):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    ("app_text", "message"),
    [
        (
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\nexport const App = () => null;\n",
            "top-level side-effect import",
        ),
        (
            'const marker = "// SZL_HF_UNIVERSAL_FRONTEND_V1";\n'
            + 'import "./szl-universal-frontend.css";\n',
            "import marker is absent",
        ),
        (
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            + 'const decoy = "import \\\"./szl-universal-frontend.css\\\";";\n',
            "top-level side-effect import",
        ),
        (
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            + 'if (false) { void import("./szl-universal-frontend.css"); }\n',
            "top-level side-effect import",
        ),
        (
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\nimport './other.css';\n",
            "top-level side-effect import",
        ),
        (
            "// SZL_HF_UNIVERSAL_FRONTEND_V1\n"
            + "export const App = () => (\n"
            + "  <main>\n"
            + '    import "./szl-universal-frontend.css";\n'
            + "  </main>\n"
            + ");\n",
            "top-level side-effect import",
        ),
    ],
)
def test_react_marker_must_have_live_declared_stylesheet_import(
    tmp_path: Path,
    app_text: str,
    message: str,
) -> None:
    _fixture(tmp_path, "react")
    app = tmp_path / "main.tsx"
    app.write_text(app_text, encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["main.tsx"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match=message):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_static_duplicate_controlled_attributes_are_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        '<link rel="stylesheet" href="./other.css" '
        'href="./szl-universal-frontend.css" '
        'data-szl-universal-frontend="v1">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["index.html"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="duplicate controlled attributes"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


@pytest.mark.parametrize(
    ("markup", "message"),
    [
        (
            '<template/><link rel="stylesheet" '
            + 'href="./szl-universal-frontend.css" '
            + 'data-szl-universal-frontend="v1">',
            "self-closing <template>",
        ),
        (
            '<template></noscript><link rel="stylesheet" '
            + 'href="./szl-universal-frontend.css" '
            + 'data-szl-universal-frontend="v1"></template>',
            "mismatched inert containers",
        ),
        ("<template>", "unclosed inert container"),
    ],
)
def test_malformed_inert_containers_fail_closed(
    tmp_path: Path,
    markup: str,
    message: str,
) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        f"{markup}</head><body></body></html>",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["index.html"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match=message):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_static_entry_file_cannot_substitute_for_served_app(tmp_path: Path) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    decoy = tmp_path / "proof.html"
    decoy.write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        '<link rel="stylesheet" href="./szl-universal-frontend.css" '
        'data-szl-universal-frontend="v1">'
        "</head><body></body></html>",
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["entry_file"] = "proof.html"
    payload["file_sha256"]["index.html"] = _sha(app)
    payload["file_sha256"]["proof.html"] = _sha(decoy)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="stylesheet <link>"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_active_css_controls_pass_with_unrelated_comments(tmp_path: Path) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text("/* explanatory comment */\n" + CSS, encoding="utf-8")
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    assert MODULE.validate(
        tmp_path,
        Path("docs/hf-universal-frontend-v1.json"),
    )["status"] == "PASS"


def test_static_base_url_override_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    app = tmp_path / "index.html"
    app.write_text(
        app.read_text(encoding="utf-8").replace(
            "<head>",
            '<head><base href="https://example.invalid/">',
        ),
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["index.html"] = _sha(app)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="may not override.*<base>"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_identifier_wrapping_contract_is_required(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    payload["contract"]["technical_identifier_wrapping_required"] = False
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        MODULE.ContractError,
        match="technical_identifier_wrapping_required must be true",
    ):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_overlong_short_description_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("Governed example", "x" * 61),
        encoding="utf-8",
    )
    manifest_path, payload = _manifest(tmp_path)
    payload["file_sha256"]["README.md"] = _sha(readme)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="exceeds 60"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_manifest_path_with_line_break_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path, payload = _manifest(tmp_path)
    payload["css_file"] = "szl-universal-frontend.css\napp_file=unverified.py"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="CR or LF"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_github_output_is_bounded(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    output = tmp_path / "github-output"
    MODULE.write_github_output(output, result)
    lines = dict(line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines())
    assert lines["status"] == "PASS"
    assert lines["framework"] == "static"
    assert len(lines["manifest_sha256"]) == 64


@pytest.mark.parametrize(
    ("field", "injected"),
    [
        ("app_file", "index.html\nstatus=FAIL"),
        ("css_file", "style.css\rmanifest_sha256=unverified"),
    ],
)
def test_github_output_rejects_line_breaks_before_writing(
    tmp_path: Path,
    field: str,
    injected: str,
) -> None:
    _fixture(tmp_path)
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    result[field] = injected
    output = tmp_path / "github-output"
    output.write_text("existing=preserved\n", encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="may not contain CR or LF"):
        MODULE.write_github_output(output, result)
    assert output.read_text(encoding="utf-8") == "existing=preserved\n"
