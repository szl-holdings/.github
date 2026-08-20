#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
from html.parser import HTMLParser
import io
import json
import posixpath
import re
import tokenize
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

SCHEMA = "szl.hf-universal-frontend/v1"
ALLOWED_FRAMEWORKS = {"static", "gradio", "streamlit", "react"}
FRAMEWORK_SDKS = {
    "static": frozenset({"static"}),
    "gradio": frozenset({"gradio"}),
    "streamlit": frozenset({"streamlit", "docker"}),
    "react": frozenset({"static", "docker"}),
}
PYTHON_MARKER = "# SZL_HF_UNIVERSAL_FRONTEND_V1"
REACT_MARKER = "// SZL_HF_UNIVERSAL_FRONTEND_V1"
REQUIRED_CSS_DECLARATIONS = {
    "--szl-touch-target": "44px",
    "overflow-wrap": "anywhere",
    "overflow-x": "clip",
}
REQUIRED_MEDIA_QUERIES = {
    "(max-width:560px)",
    "(prefers-reduced-motion:reduce)",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_OUTPUT_VALUE_BYTES = 4096


class ContractError(RuntimeError):
    pass


class _StaticDocumentParser(HTMLParser):
    _INERT_CONTAINERS = frozenset({"noscript", "template"})
    _FOREIGN_CONTAINERS = frozenset({"math", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_viewport = False
        self.has_base = False
        self.stylesheet_links: list[dict[str, str]] = []
        self._inert_stack: list[str] = []
        self._foreign_stack: list[str] = []

    @property
    def has_unclosed_inert_container(self) -> bool:
        return bool(self._inert_stack)

    @property
    def has_unclosed_foreign_container(self) -> bool:
        return bool(self._foreign_stack)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if self._foreign_stack:
            if normalized_tag in self._FOREIGN_CONTAINERS:
                self._foreign_stack.append(normalized_tag)
            return
        if normalized_tag in self._INERT_CONTAINERS:
            self._inert_stack.append(normalized_tag)
            return
        if self._inert_stack:
            return
        if normalized_tag in self._FOREIGN_CONTAINERS:
            self._foreign_stack.append(normalized_tag)
            return
        self._record(tag, attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if self._foreign_stack:
            return
        if normalized_tag in self._INERT_CONTAINERS:
            raise ContractError(
                f"Static application contains self-closing <{normalized_tag}>"
            )
        if self._inert_stack:
            return
        self._record(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if self._foreign_stack:
            if normalized_tag in self._FOREIGN_CONTAINERS:
                expected = self._foreign_stack[-1]
                if normalized_tag != expected:
                    raise ContractError(
                        "Static application contains mismatched foreign containers: "
                        f"expected </{expected}>, received </{normalized_tag}>"
                    )
                self._foreign_stack.pop()
            return
        if not self._inert_stack or normalized_tag not in self._INERT_CONTAINERS:
            return
        expected = self._inert_stack[-1]
        if normalized_tag != expected:
            raise ContractError(
                "Static application contains mismatched inert containers: "
                f"expected </{expected}>, received </{normalized_tag}>"
            )
        self._inert_stack.pop()

    def _record(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values: dict[str, str] = {}
        duplicates: set[str] = set()
        for name, value in attrs:
            key = str(name).casefold()
            if key in values:
                duplicates.add(key)
                continue
            values[key] = "" if value is None else str(value)
        normalized_tag = tag.casefold()
        if normalized_tag == "base":
            self.has_base = True
            return
        if normalized_tag == "meta" and values.get("name", "").casefold() == "viewport":
            self.has_viewport = True
        if normalized_tag != "link":
            return
        security_attributes = {
            "rel",
            "href",
            "data-szl-universal-frontend",
            "disabled",
            "media",
            "type",
        }
        ambiguous = sorted(duplicates & security_attributes)
        if ambiguous:
            raise ContractError(
                "Static stylesheet link contains duplicate controlled attributes: "
                + ", ".join(ambiguous)
            )
        rel_tokens = {
            token.casefold()
            for token in values.get("rel", "").split()
            if token.strip()
        }
        if "stylesheet" not in rel_tokens or "alternate" in rel_tokens:
            return
        if "disabled" in values:
            return
        media = values.get("media", "").strip().casefold()
        if media not in {"", "all"}:
            return
        content_type = values.get("type", "").strip().casefold()
        if content_type not in {"", "text/css"}:
            return
        self.stylesheet_links.append(values)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_line_breaks(value: str, label: str) -> None:
    if "\r" in value or "\n" in value:
        raise ContractError(f"{label} may not contain CR or LF characters")


def safe_path(root: Path, value: Any, label: str) -> Path:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} is absent or not a string")
    _reject_line_breaks(value, label)
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ContractError(f"{label} must be a safe repository-relative path: {value!r}")
    resolved_root = root.resolve()
    unresolved = resolved_root / relative
    cursor = resolved_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            raise ContractError(f"{label} may not contain a symlink: {value!r}")
    path = unresolved.resolve()
    try:
        path.relative_to(resolved_root)
    except ValueError as error:
        raise ContractError(f"{label} escapes the repository root: {value!r}") from error
    if not path.is_file():
        raise ContractError(f"{label} does not exist: {value!r}")
    return path


def parse_front_matter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ContractError("README.md must start with Hugging Face YAML front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ContractError("README.md Hugging Face front matter is not terminated")
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        key = match.group(1)
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key in values:
            duplicates.add(key)
        values[key] = value.strip()
    if duplicates:
        raise ContractError("README.md contains duplicate front-matter keys: " + ", ".join(sorted(duplicates)))
    return values


def validate_front_matter(values: dict[str, str], manifest: dict[str, Any]) -> str:
    short = values.get("short_description") or values.get("shortDescription")
    if not short:
        raise ContractError("short_description is absent")
    if len(short) > 60:
        raise ContractError(f"short_description exceeds 60 characters: {len(short)}")
    if values.get("fullWidth", "").lower() != "true":
        raise ContractError("fullWidth must be true")
    if values.get("header") != "mini":
        raise ContractError("header must be mini")
    sdk = values.get("sdk")
    if not sdk:
        raise ContractError("sdk is absent from README.md front matter")
    app_file = values.get("app_file") or values.get("appFile")
    if app_file and app_file != manifest.get("app_file"):
        raise ContractError(
            f"README app_file {app_file!r} diverges from manifest app_file {manifest.get('app_file')!r}"
        )
    return sdk.strip().casefold()


def validate_sdk_binding(card_sdk: str, manifest: dict[str, Any], framework: str) -> str:
    manifest_sdk = manifest.get("sdk")
    if not isinstance(manifest_sdk, str) or not manifest_sdk.strip():
        raise ContractError("manifest sdk is absent or not a string")
    normalized = manifest_sdk.strip().casefold()
    if card_sdk != normalized:
        raise ContractError(
            f"README sdk {card_sdk!r} diverges from manifest sdk {normalized!r}"
        )
    compatible = FRAMEWORK_SDKS[framework]
    if normalized not in compatible:
        allowed = ", ".join(sorted(compatible))
        raise ContractError(
            f"sdk {normalized!r} is not compatible with framework {framework!r}; expected one of: {allowed}"
        )
    return normalized


def _strip_css_inert_text(css_text: str) -> str:
    """Blank comments and strings without joining tokens across them."""
    output: list[str] = []
    index = 0

    def blank(character: str) -> str:
        return character if character in {"\r", "\n"} else " "

    while index < len(css_text):
        if css_text.startswith("/*", index):
            output.extend((" ", " "))
            index += 2
            while index < len(css_text):
                if css_text.startswith("*/", index):
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append(blank(css_text[index]))
                index += 1
            continue

        character = css_text[index]
        if character not in {"'", '"'}:
            output.append(character)
            index += 1
            continue

        quote = character
        output.append(" ")
        index += 1
        while index < len(css_text):
            character = css_text[index]
            output.append(blank(character))
            index += 1
            if character == "\\" and index < len(css_text):
                output.append(blank(css_text[index]))
                index += 1
                continue
            if character == quote:
                break

    return "".join(output)


def _css_rule_blocks(css_text: str) -> list[tuple[str, str]]:
    """Return top-level CSS rule preludes and bodies, failing on bad braces."""
    blocks: list[tuple[str, str]] = []
    start = 0
    cursor = 0
    while cursor < len(css_text):
        character = css_text[cursor]
        if character == "}":
            raise ContractError("universal CSS contains an unmatched closing brace")
        if character == ";":
            start = cursor + 1
            cursor += 1
            continue
        if character != "{":
            cursor += 1
            continue

        prelude = css_text[start:cursor].strip()
        depth = 1
        body_start = cursor + 1
        cursor += 1
        while cursor < len(css_text) and depth:
            if css_text[cursor] == "{":
                depth += 1
            elif css_text[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth:
            raise ContractError("universal CSS contains an unclosed rule block")
        if prelude:
            blocks.append((prelude, css_text[body_start : cursor - 1]))
        start = cursor
    return blocks


def _css_declarations(rule_body: str) -> list[tuple[str, str]]:
    """Parse declarations at the current rule level, ignoring nested rules."""
    flattened: list[str] = []
    brace_depth = 0
    for character in rule_body:
        if character == "{":
            brace_depth += 1
            flattened.append(" ")
        elif character == "}":
            if brace_depth == 0:
                raise ContractError("universal CSS contains an unmatched closing brace")
            brace_depth -= 1
            flattened.append(" ")
        elif brace_depth:
            flattened.append("\n" if character == "\n" else " ")
        else:
            flattened.append(character)
    if brace_depth:
        raise ContractError("universal CSS contains an unclosed nested rule")

    declarations: list[tuple[str, str]] = []
    for declaration in "".join(flattened).split(";"):
        if ":" not in declaration:
            continue
        property_name, value = declaration.split(":", 1)
        normalized_property = property_name.strip().casefold()
        normalized_value = re.sub(r"\s+", "", value).casefold()
        normalized_value = re.sub(r"!important$", "", normalized_value)
        if normalized_property and normalized_value:
            declarations.append((normalized_property, normalized_value))
    return declarations


def _media_query(prelude: str) -> str | None:
    match = re.fullmatch(r"@media\s+(.+)", prelude.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return re.sub(r"\s+", "", match.group(1)).casefold()


def _has_reduced_motion_control(declarations: list[tuple[str, str]]) -> bool:
    accepted = {
        ("animation", "none"),
        ("animation-duration", "0s"),
        ("animation-duration", "0ms"),
        ("animation-duration", "0.01ms"),
        ("transition", "none"),
        ("transition-duration", "0s"),
        ("transition-duration", "0ms"),
        ("transition-duration", "0.01ms"),
        ("scroll-behavior", "auto"),
    }
    return any(declaration in accepted for declaration in declarations)


def _selector_is_guaranteed_active(prelude: str) -> bool:
    """Accept only selectors guaranteed to match the served document.

    The contract cannot inspect runtime component markup, so class, attribute,
    state, and negation selectors are not evidence that a declaration applies.
    A selector list is usable when it includes the document root/body or the
    universal selector directly.
    """
    guaranteed = {":root", "html", "body", "*"}
    audited = guaranteed | {"*::before", "*::after"}
    selectors = {
        re.sub(r"\s+", "", selector).casefold()
        for selector in prelude.split(",")
        if selector.strip()
    }
    return bool(selectors & guaranteed) and selectors <= audited


def validate_css(css_text: str) -> None:
    active_css = _strip_css_inert_text(css_text)
    active_declarations: set[tuple[str, str]] = set()
    observed_media: set[str] = set()
    for prelude, body in _css_rule_blocks(active_css):
        if not prelude.lstrip().startswith("@"):
            if _selector_is_guaranteed_active(prelude):
                active_declarations.update(_css_declarations(body))
            continue
        query = _media_query(prelude)
        if query not in REQUIRED_MEDIA_QUERIES:
            continue
        nested_declarations: list[tuple[str, str]] = []
        for nested_prelude, nested_body in _css_rule_blocks(body):
            if nested_prelude.lstrip().startswith("@"):
                continue
            if not _selector_is_guaranteed_active(nested_prelude):
                continue
            nested_declarations.extend(_css_declarations(nested_body))
        if not nested_declarations:
            continue
        if query == "(prefers-reduced-motion:reduce)" and not _has_reduced_motion_control(
            nested_declarations
        ):
            continue
        observed_media.add(query)

    missing = [
        f"{name}: {value}"
        for name, value in REQUIRED_CSS_DECLARATIONS.items()
        if (name, value) not in active_declarations
    ]
    missing.extend(
        f"@media {query}"
        for query in sorted(REQUIRED_MEDIA_QUERIES - observed_media)
    )
    if missing:
        raise ContractError("universal CSS is missing required active tokens: " + ", ".join(missing))


def _parse_python(app_text: str) -> ast.Module:
    try:
        return ast.parse(app_text)
    except SyntaxError as error:
        raise ContractError(f"Python frontend binding is not valid syntax: {error}") from error


def _has_python_marker(app_text: str) -> bool:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(app_text).readline)
        return any(
            token.type == tokenize.COMMENT and token.string.strip() == PYTHON_MARKER
            for token in tokens
        )
    except tokenize.TokenError as error:
        raise ContractError(f"Python frontend binding cannot be tokenized: {error}") from error


def _path_aliases(tree: ast.Module) -> set[str]:
    aliases: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module != "pathlib":
            continue
        for imported in node.names:
            if imported.name == "Path":
                aliases.add(imported.asname or imported.name)
    shadowed = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    shadowed.update(
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    )
    return aliases - shadowed


def _loads_declared_css(expression: ast.AST, css_file: str, path_aliases: set[str]) -> bool:
    if not isinstance(expression, ast.Call) or not isinstance(expression.func, ast.Attribute):
        return False
    if expression.func.attr != "read_text" or expression.args:
        return False
    path_call = expression.func.value
    if not isinstance(path_call, ast.Call) or len(path_call.args) != 1:
        return False
    if not isinstance(path_call.func, ast.Name) or path_call.func.id not in path_aliases:
        return False
    literal = path_call.args[0]
    return isinstance(literal, ast.Constant) and literal.value == css_file


def _css_binding_variables(
    tree: ast.Module,
    css_file: str,
    path_aliases: set[str],
) -> set[str]:
    variables: set[str] = set()
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if value is None or not _loads_declared_css(value, css_file, path_aliases):
            continue
        variables.update(target.id for target in targets if isinstance(target, ast.Name))
    store_counts = {
        variable: sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Store)
            and node.id == variable
        )
        for variable in variables
    }
    return {variable for variable in variables if store_counts[variable] == 1}


def _module_aliases(tree: ast.Module, module: str) -> set[str]:
    aliases: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for imported in node.names:
            if imported.name == module:
                aliases.add(imported.asname or imported.name)
    shadowed = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    shadowed.update(
        node.arg for node in ast.walk(tree) if isinstance(node, ast.arg)
    )
    return aliases - shadowed


def _direct_top_level_calls(tree: ast.Module) -> list[ast.Call]:
    """Return calls in the narrow module statements guaranteed to execute.

    Calls under functions, classes, conditionals, loops, exception handlers,
    and comprehensions are intentionally excluded because static inspection
    cannot prove that those paths run. Top-level ``with`` bodies are accepted;
    entering the context and executing its body are unconditional module work.
    """
    calls: list[ast.Call] = []

    def collect(statements: list[ast.stmt]) -> None:
        for statement in statements:
            expression: ast.AST | None = None
            if isinstance(statement, ast.Expr):
                expression = statement.value
            elif isinstance(statement, ast.Assign):
                expression = statement.value
            elif isinstance(statement, ast.AnnAssign):
                expression = statement.value
            if isinstance(expression, ast.Call):
                calls.append(expression)
                continue
            if isinstance(statement, (ast.With, ast.AsyncWith)):
                calls.extend(
                    item.context_expr
                    for item in statement.items
                    if isinstance(item.context_expr, ast.Call)
                )
                collect(statement.body)

    collect(tree.body)
    return calls


def _gradio_applies_css(tree: ast.Module, css_variables: set[str]) -> bool:
    aliases = _module_aliases(tree, "gradio")
    constructors = {"Blocks", "ChatInterface", "Interface", "TabbedInterface"}
    for node in _direct_top_level_calls(tree):
        if not isinstance(node.func, ast.Attribute):
            continue
        if (
            not isinstance(node.func.value, ast.Name)
            or node.func.value.id not in aliases
            or node.func.attr not in constructors
        ):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "css"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id in css_variables
            ):
                return True
    return False


def _style_expression_parts(
    expression: ast.AST,
    css_variables: set[str],
) -> list[str] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return [expression.value]
    if isinstance(expression, ast.Name) and expression.id in css_variables:
        return ["<DECLARED_CSS>"]
    if isinstance(expression, ast.FormattedValue):
        return _style_expression_parts(expression.value, css_variables)
    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []
        for value in expression.values:
            nested = _style_expression_parts(value, css_variables)
            if nested is None:
                return None
            parts.extend(nested)
        return parts
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        left = _style_expression_parts(expression.left, css_variables)
        right = _style_expression_parts(expression.right, css_variables)
        if left is None or right is None:
            return None
        return left + right
    return None


def _style_expression_uses_css(expression: ast.AST, css_variables: set[str]) -> bool:
    parts = _style_expression_parts(expression, css_variables)
    if parts is None or "<DECLARED_CSS>" not in parts:
        return False
    rendered = "".join(parts).casefold()
    return "<style" in rendered and "</style>" in rendered


def _streamlit_applies_css(tree: ast.Module, css_variables: set[str]) -> bool:
    aliases = _module_aliases(tree, "streamlit")
    for node in _direct_top_level_calls(tree):
        if not isinstance(node.func, ast.Attribute):
            continue
        if (
            not isinstance(node.func.value, ast.Name)
            or node.func.value.id not in aliases
            or node.func.attr != "markdown"
            or not node.args
        ):
            continue
        unsafe = next(
            (keyword.value for keyword in node.keywords if keyword.arg == "unsafe_allow_html"),
            None,
        )
        if (
            isinstance(unsafe, ast.Constant)
            and unsafe.value is True
            and _style_expression_uses_css(node.args[0], css_variables)
        ):
            return True
    return False


def _consume_javascript_string(
    source: str,
    start: int,
    *,
    reject_escapes: bool = False,
) -> tuple[str, int] | None:
    quote = source[start]
    cursor = start + 1
    value: list[str] = []
    while cursor < len(source):
        character = source[cursor]
        if character == "\\":
            if reject_escapes:
                # Escaped module specifiers are not an exact, auditable path form.
                return None
            if cursor + 1 >= len(source):
                return None
            value.extend((character, source[cursor + 1]))
            cursor += 2
            continue
        if character == quote:
            return "".join(value), cursor + 1
        if quote != "`" and character in {"\r", "\n"}:
            return None
        value.append(character)
        cursor += 1
    return None


def _react_marker_and_imports(app_text: str) -> tuple[bool, list[str]]:
    """Extract exact top-level side-effect imports from JavaScript source."""
    marker = False
    imports: list[str] = []
    cursor = 0
    brace_depth = 0
    while cursor < len(app_text):
        if app_text.startswith("//", cursor):
            end = len(app_text)
            for separator in ("\r", "\n"):
                candidate = app_text.find(separator, cursor + 2)
                if candidate >= 0:
                    end = min(end, candidate)
            if brace_depth == 0 and app_text[cursor:end].strip() == REACT_MARKER:
                marker = True
            cursor = end
            continue
        if app_text.startswith("/*", cursor):
            end = app_text.find("*/", cursor + 2)
            if end < 0:
                raise ContractError("React frontend binding contains an unclosed comment")
            cursor = end + 2
            continue

        character = app_text[cursor]
        if character in {"'", '"', "`"}:
            consumed = _consume_javascript_string(app_text, cursor)
            if consumed is None:
                raise ContractError("React frontend binding contains an unsupported string literal")
            _, cursor = consumed
            continue
        if character == "{":
            brace_depth += 1
            cursor += 1
            continue
        if character == "}":
            brace_depth = max(0, brace_depth - 1)
            cursor += 1
            continue

        if (
            brace_depth == 0
            and app_text.startswith("import", cursor)
            and not app_text[
                max(app_text.rfind("\n", 0, cursor), app_text.rfind("\r", 0, cursor)) + 1 : cursor
            ].strip()
            and (cursor == 0 or not (app_text[cursor - 1].isalnum() or app_text[cursor - 1] in {"_", "$"}))
            and (
                cursor + 6 == len(app_text)
                or not (app_text[cursor + 6].isalnum() or app_text[cursor + 6] in {"_", "$"})
            )
        ):
            path_start = cursor + 6
            while path_start < len(app_text) and app_text[path_start] in {" ", "\t"}:
                path_start += 1
            if path_start < len(app_text) and app_text[path_start] in {"'", '"'}:
                consumed = _consume_javascript_string(
                    app_text,
                    path_start,
                    reject_escapes=True,
                )
                if consumed is not None:
                    specifier, end = consumed
                    terminator = re.match(
                        r"[ \t]*;?[ \t]*(?://[^\r\n]*)?(?:\r?\n|$)",
                        app_text[end:],
                    )
                    if terminator:
                        imports.append(specifier)
                        cursor = end + terminator.end()
                        continue
        cursor += 1
    return marker, imports


def _resolved_react_import(app_file: str, specifier: str) -> str:
    _reject_line_breaks(specifier, "React stylesheet import")
    parsed = urlsplit(specifier)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ContractError("React universal stylesheet import must be repository-local")
    if not parsed.path or parsed.path.startswith("/") or "\\" in parsed.path:
        raise ContractError("React universal stylesheet import must be a relative POSIX path")
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(app_file), parsed.path)
    )
    if resolved == ".." or resolved.startswith("../"):
        raise ContractError("React universal stylesheet import escapes the repository")
    return resolved


def _react_applies_css(app_text: str, app_file: str, css_file: str) -> bool:
    marker, imports = _react_marker_and_imports(app_text)
    if not marker:
        raise ContractError("React universal CSS import marker is absent")
    expected = posixpath.normpath(css_file)
    return any(
        _resolved_react_import(app_file, specifier) == expected
        for specifier in imports
    )


def _resolved_static_href(app_file: str, href: str) -> str:
    _reject_line_breaks(href, "static stylesheet href")
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        raise ContractError("static universal stylesheet href must be repository-local")
    decoded = unquote(parsed.path)
    _reject_line_breaks(decoded, "decoded static stylesheet href")
    if not decoded or decoded.startswith("/") or "\\" in decoded:
        raise ContractError("static universal stylesheet href must be a relative POSIX path")
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(app_file), decoded))
    if resolved == ".." or resolved.startswith("../"):
        raise ContractError("static universal stylesheet href escapes the application directory")
    return resolved


def validate_framework_binding(
    framework: str,
    app_text: str,
    *,
    app_file: str,
    css_file: str,
) -> None:
    if framework in {"gradio", "streamlit"}:
        if not _has_python_marker(app_text):
            raise ContractError("Python frontend binding marker is absent")
        tree = _parse_python(app_text)
        path_aliases = _path_aliases(tree)
        css_variables = _css_binding_variables(tree, css_file, path_aliases)
        if not css_variables:
            raise ContractError(
                "Python frontend binding does not read the declared CSS file"
            )
        if framework == "gradio" and not _gradio_applies_css(tree, css_variables):
            raise ContractError("Gradio universal CSS binding is absent")
        if framework == "streamlit" and not _streamlit_applies_css(
            tree, css_variables
        ):
            raise ContractError("Streamlit universal CSS binding is absent")
    if framework == "static":
        parser = _StaticDocumentParser()
        parser.feed(app_text)
        parser.close()
        if parser.has_unclosed_inert_container:
            raise ContractError("Static application contains an unclosed inert container")
        if parser.has_unclosed_foreign_container:
            raise ContractError("Static application contains an unclosed foreign container")
        if not parser.has_viewport:
            raise ContractError("Static viewport metadata is absent")
        if parser.has_base:
            raise ContractError(
                "Static application may not override repository-local URL resolution with <base>"
            )
        expected_css = posixpath.normpath(css_file)
        for link in parser.stylesheet_links:
            if link.get("data-szl-universal-frontend") != "v1":
                continue
            href = link.get("href", "")
            if _resolved_static_href(app_file, href) == expected_css:
                break
        else:
            raise ContractError(
                "Static universal CSS requires a stylesheet <link> whose marker and href bind the declared css_file"
            )
    if framework == "react" and not _react_applies_css(
        app_text,
        app_file,
        css_file,
    ):
        raise ContractError(
            "React universal CSS requires a top-level side-effect import of the declared css_file"
        )


def validate_hashes(
    root: Path, hashes: Any, required_paths: set[str]
) -> dict[str, str]:
    if not isinstance(hashes, dict) or not hashes:
        raise ContractError("file_sha256 is absent or empty")
    missing = sorted(required_paths - set(hashes))
    if missing:
        raise ContractError(
            "file_sha256 is missing managed paths: " + ", ".join(missing)
        )
    verified: dict[str, str] = {}
    for relative, expected in sorted(hashes.items()):
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            raise ContractError(f"invalid SHA-256 digest for {relative!r}")
        path = safe_path(root, relative, f"file_sha256[{relative!r}]")
        observed = sha256(path)
        if observed != expected:
            raise ContractError(
                f"file hash mismatch for {relative}: expected {expected}, observed {observed}"
            )
        verified[str(relative)] = observed
    return verified


def validate(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise ContractError(f"repository root does not exist: {root}")
    manifest_full = safe_path(root, manifest_path, "manifest")
    try:
        manifest = json.loads(manifest_full.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"manifest is not valid JSON: {error}") from error
    if not isinstance(manifest, dict):
        raise ContractError("manifest root must be a JSON object")
    if manifest.get("schema") != SCHEMA:
        raise ContractError(f"unexpected manifest schema: {manifest.get('schema')!r}")
    if manifest.get("remote_mutation") is not False:
        raise ContractError("manifest remote_mutation must be false")
    framework = manifest.get("framework")
    if framework not in ALLOWED_FRAMEWORKS:
        raise ContractError(f"unsupported framework: {framework!r}")

    # Resolve every manifest-controlled path before comparing descriptive
    # metadata. This keeps traversal and containment failures authoritative.
    readme = safe_path(root, "README.md", "README.md")
    app = safe_path(root, manifest.get("app_file"), "app_file")
    css = safe_path(root, manifest.get("css_file"), "css_file")
    entry = None
    if manifest.get("entry_file"):
        entry = safe_path(root, manifest.get("entry_file"), "entry_file")

    # Authenticate managed bytes before interpreting their contents. A changed
    # file must report hash drift rather than an incidental downstream parse or
    # framework-binding error.
    required_hashes = {
        "README.md",
        str(manifest["app_file"]),
        str(manifest["css_file"]),
    }
    if manifest.get("entry_file"):
        required_hashes.add(str(manifest["entry_file"]))
    hashes = validate_hashes(
        root, manifest.get("file_sha256"), required_hashes
    )

    front = parse_front_matter(readme.read_text(encoding="utf-8"))
    card_sdk = validate_front_matter(front, manifest)
    sdk = validate_sdk_binding(card_sdk, manifest, framework)
    validate_css(css.read_text(encoding="utf-8"))
    # A static Space serves app_file directly. entry_file is relevant to
    # source-based adapters, but it must not redirect validation to a decoy
    # document while the served HTML omits the declared stylesheet.
    binding_path = app if framework == "static" else (entry or app)
    binding_relative = (
        str(manifest["app_file"])
        if framework == "static"
        else str(manifest.get("entry_file") or manifest["app_file"])
    )
    validate_framework_binding(
        framework,
        binding_path.read_text(encoding="utf-8"),
        app_file=binding_relative,
        css_file=str(manifest["css_file"]),
    )

    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise ContractError("manifest contract is absent")
    if contract.get("minimum_touch_target_px") != 44:
        raise ContractError("minimum_touch_target_px must be 44")
    if contract.get("horizontal_overflow_allowed") is not False:
        raise ContractError("horizontal_overflow_allowed must be false")
    if contract.get("reduced_motion_required") is not True:
        raise ContractError("reduced_motion_required must be true")
    if contract.get("technical_identifier_wrapping_required") is not True:
        raise ContractError("technical_identifier_wrapping_required must be true")
    viewports = contract.get("viewport_classes")
    if viewports != [360, 390, 768, 1024, 1440]:
        raise ContractError(f"unexpected viewport_classes: {viewports!r}")

    return {
        "schema": "szl.hf-universal-frontend-contract-result/v1",
        "status": "PASS",
        "framework": framework,
        "sdk": sdk,
        "app_file": manifest.get("app_file"),
        "css_file": manifest.get("css_file"),
        "entry_file": manifest.get("entry_file"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256(manifest_full),
        "verified_files": hashes,
        "remote_mutation": False,
    }


def _github_output_value(name: str, value: Any) -> str:
    text = "" if value is None else str(value)
    _reject_line_breaks(text, f"GitHub output {name}")
    if len(text.encode("utf-8")) > MAX_OUTPUT_VALUE_BYTES:
        raise ContractError(
            f"GitHub output {name} exceeds {MAX_OUTPUT_VALUE_BYTES} bytes"
        )
    return text


def write_github_output(path: Path, result: dict[str, Any]) -> None:
    lines = {
        "status": result["status"],
        "framework": result["framework"],
        "app_file": result["app_file"],
        "css_file": result["css_file"],
        "manifest_sha256": result["manifest_sha256"],
    }
    # Authenticate every value before opening the environment file. A rejected
    # value must not leave a partial set of outputs behind.
    records = [
        f"{key}={_github_output_value(key, value)}\n"
        for key, value in lines.items()
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(records)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/hf-universal-frontend-v1.json"),
    )
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    try:
        result = validate(args.root, args.manifest)
        if args.github_output:
            write_github_output(args.github_output, result)
    except (ContractError, OSError, ValueError) as error:
        print(json.dumps({"status": "FAIL", "error": str(error)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
