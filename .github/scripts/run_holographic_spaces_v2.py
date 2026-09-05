#!/usr/bin/env python3
"""Execute the Holographic Space Fabric controller with hardened adapters."""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"unable to load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


core = load_module(
    "szl_holographic_space_core",
    HERE / "rollout_holographic_spaces_v2.py",
)


def _fixed_streamlit_adapter(content: str, slug: str) -> str:
    marker = "# SZL Holographic Space Fabric v2"
    if marker in content:
        return content
    try:
        module = ast.parse(content)
    except SyntaxError as exc:
        raise core.RolloutError("PYTHON_PARSE_FAILED", str(exc)) from exc

    import_at = core.python_import_offset(module, content)
    addition = "\n# SZL Holographic Space Fabric v2\nfrom szl_hologram_streamlit import render_szl_hologram\n"
    output = content[:import_at] + addition + content[import_at:]
    try:
        patched = ast.parse(output)
    except SyntaxError as exc:
        raise core.RolloutError("STREAMLIT_IMPORT_FAILED", str(exc)) from exc

    offsets = core.line_offsets(output)
    calls = [
        node
        for node in ast.walk(patched)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_page_config"
    ]
    if calls:
        _, insert_at = core.node_span(
            min(calls, key=lambda item: (item.lineno, item.col_offset)),
            offsets,
        )
    else:
        imports = [
            node
            for node in patched.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        if imports:
            _, insert_at = core.node_span(imports[-1], offsets)
        else:
            insert_at = core.python_import_offset(patched, output)

    output = output[:insert_at] + f"\nrender_szl_hologram({slug!r})\n" + output[insert_at:]
    compile(output, "app.py", "exec")
    return output


core.adapt_streamlit = _fixed_streamlit_adapter

# Install the additive responsive refresh before the source-authority and target
# contracts so publisher-managed surfaces cannot be converted back into guessed
# product-repository edits by an inner adapter.
responsive = load_module(
    "szl_responsive_space_contract",
    HERE / "responsive_space_contract.py",
)
responsive.install(core)

authority = load_module(
    "szl_source_authority_contract",
    HERE / "source_authority_contract.py",
)
authority.install(core)

targets = load_module(
    "szl_holographic_target_contract",
    HERE / "holographic_target_contract.py",
)
targets.install(core)


if __name__ == "__main__":
    try:
        raise SystemExit(core.main())
    except core.RolloutError as exc:
        import json

        print(
            json.dumps({"status": "blocked", "error": exc.as_dict()}, indent=2, sort_keys=True),
            file=sys.stderr,
        )
        raise SystemExit(2)
