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

CSS = """--szl-touch-target: 44px;
overflow-wrap: anywhere;
overflow-x: clip;
@media (max-width: 560px) {}
@media (prefers-reduced-motion: reduce) {}
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
    elif framework == "gradio":
        app = root / "app.py"
        app.write_text(
            "# SZL_HF_UNIVERSAL_FRONTEND_V1\n_SZL_UNIVERSAL_CSS = 'x'\n",
            encoding="utf-8",
        )
        app_file = "app.py"
    else:
        raise AssertionError(framework)
    css = root / "szl-universal-frontend.css"
    css.write_text(CSS, encoding="utf-8")
    (root / "README.md").write_text(
        "---\n"
        "title: Example\n"
        "sdk: static\n"
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
        "sdk": "static",
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


def test_static_contract_passes(tmp_path: Path) -> None:
    _fixture(tmp_path)
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["status"] == "PASS"
    assert result["framework"] == "static"
    assert result["remote_mutation"] is False


def test_gradio_contract_passes(tmp_path: Path) -> None:
    _fixture(tmp_path, "gradio")
    result = MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))
    assert result["framework"] == "gradio"


def test_hash_drift_fails_closed(tmp_path: Path) -> None:
    _fixture(tmp_path)
    (tmp_path / "index.html").write_text("drift", encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="hash mismatch"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    manifest_path = tmp_path / "docs" / "hf-universal-frontend-v1.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["app_file"] = "../outside.py"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="safe repository-relative path"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_missing_css_control_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    css = tmp_path / "szl-universal-frontend.css"
    css.write_text(CSS.replace("overflow-x: clip;", ""), encoding="utf-8")
    manifest_path = tmp_path / "docs" / "hf-universal-frontend-v1.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["file_sha256"]["szl-universal-frontend.css"] = _sha(css)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="missing required tokens"):
        MODULE.validate(tmp_path, Path("docs/hf-universal-frontend-v1.json"))


def test_overlong_short_description_is_rejected(tmp_path: Path) -> None:
    _fixture(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8").replace("Governed example", "x" * 61), encoding="utf-8")
    manifest_path = tmp_path / "docs" / "hf-universal-frontend-v1.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["file_sha256"]["README.md"] = _sha(readme)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(MODULE.ContractError, match="exceeds 60"):
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
