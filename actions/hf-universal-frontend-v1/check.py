#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import codecs
import hashlib
import io
import json
import posixpath
import re
import tokenize
from html.parser import HTMLParser
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
HTML_ASCII_WHITESPACE = " \t\n\f\r"
CSS_WHITESPACE = " \t\r\n\f"
CSS_WHITESPACE_PATTERN = r"[ \t\r\n\f]"


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
        rel_value = values.get("rel", "").strip(HTML_ASCII_WHITESPACE)
        rel_tokens = {
            token.casefold()
            for token in re.split(r"[ \t\n\f\r]+", rel_value)
            if token
        }
        if "stylesheet" not in rel_tokens or "alternate" in rel_tokens:
            return
        if "disabled" in values:
            return
        # CSS media queries recognize only CSS whitespace. Unicode whitespace
        # such as NBSP remains part of the query and must not be erased into an
        # apparently empty or ``all`` query.
        media = values.get("media", "").strip(CSS_WHITESPACE).casefold()
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

        prelude = css_text[start:cursor].strip(CSS_WHITESPACE)
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


def _css_declarations(rule_body: str) -> list[tuple[str, str, bool]]:
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

    declarations: list[tuple[str, str, bool]] = []
    for declaration in "".join(flattened).split(";"):
        if ":" not in declaration:
            continue
        property_name, value = declaration.split(":", 1)
        normalized_property = property_name.strip(CSS_WHITESPACE)
        # Standard CSS property names are ASCII case-insensitive, but custom
        # properties are case-sensitive. ``--SZL-TOUCH-TARGET`` therefore
        # defines a different variable from the contract's lowercase name.
        if not normalized_property.startswith("--"):
            normalized_property = normalized_property.casefold()
        # Whitespace separates CSS tokens. Removing it would turn invalid or
        # different values such as ``44 px`` and ``any where`` into the
        # required ``44px`` and ``anywhere`` controls. Collapse runs instead,
        # then remove only the syntactically separate !important annotation.
        normalized_value = re.sub(
            CSS_WHITESPACE_PATTERN + "+",
            " ",
            value.strip(CSS_WHITESPACE),
        ).casefold()
        important_pattern = (
            CSS_WHITESPACE_PATTERN
            + "*!"
            + CSS_WHITESPACE_PATTERN
            + "*important"
            + CSS_WHITESPACE_PATTERN
            + "*$"
        )
        important = re.search(important_pattern, normalized_value) is not None
        normalized_value = re.sub(
            important_pattern,
            "",
            normalized_value,
        ).rstrip(CSS_WHITESPACE)
        if normalized_property and normalized_value:
            declarations.append((normalized_property, normalized_value, important))
    return declarations


def _media_query(prelude: str) -> str | None:
    match = re.fullmatch(
        r"@media[ \t\r\n\f]+(.+)",
        prelude.strip(CSS_WHITESPACE),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    query = match.group(1)
    recognized = {
        r"\([ \t\r\n\f]*max-width[ \t\r\n\f]*:[ \t\r\n\f]*560px[ \t\r\n\f]*\)": "(max-width:560px)",
        r"\([ \t\r\n\f]*prefers-reduced-motion[ \t\r\n\f]*:[ \t\r\n\f]*reduce[ \t\r\n\f]*\)": "(prefers-reduced-motion:reduce)",
    }
    for pattern, normalized in recognized.items():
        if re.fullmatch(pattern, query, flags=re.IGNORECASE):
            return normalized
    return None


def _has_reduced_motion_control(
    declarations: dict[tuple[str, str], tuple[str, bool]],
) -> bool:
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
    return any(
        (property_name, value) in accepted
        for (_, property_name), (value, _) in declarations.items()
    )


def _guaranteed_active_selectors(prelude: str) -> set[str]:
    """Accept only selectors guaranteed to match the served document.

    The contract cannot inspect runtime component markup, so class, attribute,
    state, and negation selectors are not evidence that a declaration applies.
    A selector list is usable when it includes the document root/body or the
    universal selector directly.
    """
    guaranteed = {":root", "html", "body", "*"}
    audited = guaranteed | {"*::before", "*::after"}
    # Whitespace inside a selector is semantic: it is the descendant
    # combinator.  Removing it would turn an unrelated selector such as
    # ``h t m l`` into the guaranteed document selector ``html``.
    selector_items = prelude.split(",")
    if any(not selector.strip(CSS_WHITESPACE) for selector in selector_items):
        return set()
    selectors = {
        selector.strip(CSS_WHITESPACE).casefold() for selector in selector_items
    }
    if not selectors & guaranteed or not selectors <= audited:
        return set()
    return selectors


def _update_cascade(
    cascade: dict[tuple[str, str], tuple[str, bool]],
    selectors: set[str],
    declarations: list[tuple[str, str, bool]],
) -> None:
    """Record final same-selector declarations, honoring ``!important``."""
    for property_name, value, important in declarations:
        for selector in selectors:
            key = (selector, property_name)
            previous = cascade.get(key)
            if previous is not None and previous[1] and not important:
                continue
            cascade[key] = (value, important)


def validate_css(css_text: str) -> None:
    active_css = _strip_css_inert_text(css_text)
    active_declarations: dict[tuple[str, str], tuple[str, bool]] = {}
    media_declarations: dict[
        str,
        dict[tuple[str, str], tuple[str, bool]],
    ] = {query: {} for query in REQUIRED_MEDIA_QUERIES}
    for prelude, body in _css_rule_blocks(active_css):
        if not prelude.lstrip(CSS_WHITESPACE).startswith("@"):
            selectors = _guaranteed_active_selectors(prelude)
            if selectors:
                _update_cascade(
                    active_declarations,
                    selectors,
                    _css_declarations(body),
                )
            continue
        query = _media_query(prelude)
        if query not in REQUIRED_MEDIA_QUERIES:
            continue
        for nested_prelude, nested_body in _css_rule_blocks(body):
            if nested_prelude.lstrip(CSS_WHITESPACE).startswith("@"):
                continue
            selectors = _guaranteed_active_selectors(nested_prelude)
            if not selectors:
                continue
            _update_cascade(
                media_declarations[query],
                selectors,
                _css_declarations(nested_body),
            )

    observed_media = {
        query
        for query, declarations in media_declarations.items()
        if declarations
        and (
            query != "(prefers-reduced-motion:reduce)"
            or _has_reduced_motion_control(declarations)
        )
    }

    missing = [
        f"{name}: {value}"
        for name, value in REQUIRED_CSS_DECLARATIONS.items()
        if not any(
            property_name == name and declaration_value == value
            for (_, property_name), (
                declaration_value,
                _,
            ) in active_declarations.items()
        )
    ]
    missing.extend(
        f"@media {query}"
        for query in sorted(REQUIRED_MEDIA_QUERIES - observed_media)
    )
    if missing:
        raise ContractError("universal CSS is missing required active tokens: " + ", ".join(missing))


def _parse_python(app_text: str) -> ast.Module:
    try:
        # ast.parse alone can construct trees for forms the bytecode compiler
        # rejects, including repeated keyword arguments. Such a module cannot
        # execute the claimed framework binding.
        compile(app_text, "<hf-universal-frontend>", "exec")
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


SourcePosition = tuple[int, int]


def _source_position(node: ast.AST) -> SourcePosition:
    return (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


def _store_bound_names(tree: ast.Module) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _non_store_bound_names(tree: ast.Module) -> set[str]:
    names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Del)
    }
    names.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    names.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    names.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler) and node.name is not None
    )
    names.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name is not None
    )
    names.update(
        node.rest
        for node in ast.walk(tree)
        if isinstance(node, ast.MatchMapping) and node.rest is not None
    )
    return names


def _import_binding_counts(tree: ast.Module) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bindings = [
                imported.asname or imported.name.split(".", 1)[0]
                for imported in node.names
            ]
        elif isinstance(node, ast.ImportFrom):
            bindings = [imported.asname or imported.name for imported in node.names]
        else:
            continue
        for name in bindings:
            counts[name] = counts.get(name, 0) + 1
    return counts


def _path_aliases(tree: ast.Module) -> dict[str, SourcePosition]:
    aliases: dict[str, SourcePosition] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module != "pathlib":
            continue
        for imported in node.names:
            if imported.name == "Path":
                name = imported.asname or imported.name
                position = _source_position(node)
                if name not in aliases or position < aliases[name]:
                    aliases[name] = position
    shadowed = _store_bound_names(tree) | _non_store_bound_names(tree)
    import_counts = _import_binding_counts(tree)
    return {
        name: position
        for name, position in aliases.items()
        if name not in shadowed and import_counts.get(name) == 1
    }


def _loads_declared_css(
    expression: ast.AST,
    css_file: str,
    path_aliases: dict[str, SourcePosition],
) -> bool:
    if not isinstance(expression, ast.Call) or not isinstance(
        expression.func, ast.Attribute
    ):
        return False
    if expression.func.attr != "read_text" or expression.args:
        return False
    read_options: dict[str, str | None] = {}
    for keyword in expression.keywords:
        if keyword.arg not in {"encoding", "errors"} or keyword.arg in read_options:
            return False
        if not isinstance(keyword.value, ast.Constant) or not (
            keyword.value.value is None or isinstance(keyword.value.value, str)
        ):
            return False
        read_options[keyword.arg] = keyword.value.value
    encoding = read_options.get("encoding")
    if encoding is not None:
        try:
            codec_name = codecs.lookup(encoding).name
        except LookupError:
            return False
        # The verifier authenticates and parses the managed stylesheet as
        # UTF-8. Certifying a different decoder would not bind the adapter to
        # the same text the contract inspected.
        if codec_name != "utf-8":
            return False
    errors = read_options.get("errors")
    if errors is not None:
        try:
            codecs.lookup_error(errors)
        except LookupError:
            return False
    path_call = expression.func.value
    if (
        not isinstance(path_call, ast.Call)
        or len(path_call.args) != 1
        or path_call.keywords
    ):
        return False
    if not isinstance(path_call.func, ast.Name):
        return False
    import_position = path_aliases.get(path_call.func.id)
    if import_position is None or import_position >= _source_position(path_call):
        return False
    literal = path_call.args[0]
    return isinstance(literal, ast.Constant) and literal.value == css_file


def _css_binding_variables(
    tree: ast.Module,
    css_file: str,
    path_aliases: dict[str, SourcePosition],
) -> dict[str, SourcePosition]:
    variables: dict[str, SourcePosition] = {}
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
        for target in targets:
            if isinstance(target, ast.Name):
                variables[target.id] = _source_position(node)
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
    invalidated = _non_store_bound_names(tree) | set(_import_binding_counts(tree))
    return {
        variable: position
        for variable, position in variables.items()
        if store_counts[variable] == 1 and variable not in invalidated
    }


def _module_aliases(tree: ast.Module, module: str) -> dict[str, SourcePosition]:
    aliases: dict[str, SourcePosition] = {}
    for node in tree.body:
        if not isinstance(node, ast.Import):
            continue
        for imported in node.names:
            if imported.name == module:
                name = imported.asname or imported.name
                position = _source_position(node)
                if name not in aliases or position < aliases[name]:
                    aliases[name] = position
    shadowed = _store_bound_names(tree) | _non_store_bound_names(tree)
    import_counts = _import_binding_counts(tree)
    return {
        name: position
        for name, position in aliases.items()
        if name not in shadowed and import_counts.get(name) == 1
    }


def _literal_truth_value(expression: ast.AST) -> bool | None:
    if isinstance(expression, ast.Constant):
        return bool(expression.value)
    if isinstance(expression, ast.UnaryOp) and isinstance(expression.op, ast.Not):
        nested = _literal_truth_value(expression.operand)
        return None if nested is None else not nested
    return None


def _statements_fall_through(statements: list[ast.stmt]) -> bool:
    for statement in statements:
        if isinstance(statement, (ast.Raise, ast.Return, ast.Break, ast.Continue)):
            return False
        if (
            isinstance(statement, ast.Assert)
            and _literal_truth_value(statement.test) is False
        ):
            return False
        if not isinstance(statement, ast.If):
            continue
        truth_value = _literal_truth_value(statement.test)
        if truth_value is True:
            branch_falls_through = _statements_fall_through(statement.body)
        elif truth_value is False:
            branch_falls_through = (
                _statements_fall_through(statement.orelse)
                if statement.orelse
                else True
            )
        else:
            body_falls_through = _statements_fall_through(statement.body)
            else_falls_through = (
                _statements_fall_through(statement.orelse)
                if statement.orelse
                else True
            )
            branch_falls_through = body_falls_through or else_falls_through
        if not branch_falls_through:
            return False
    return True


def _direct_top_level_calls(tree: ast.Module) -> list[ast.Call]:
    """Return calls in the narrow module statements guaranteed to execute.

    Calls under functions, classes, conditionals, loops, exception handlers,
    and comprehensions are intentionally excluded because static inspection
    cannot prove that those paths run. Top-level ``with`` bodies are accepted;
    entering the context and executing its body are unconditional module work.
    """
    calls: list[ast.Call] = []

    def collect(statements: list[ast.stmt]) -> bool:
        """Collect calls until control can no longer reach the next statement."""
        for statement in statements:
            if isinstance(statement, (ast.Raise, ast.Return, ast.Break, ast.Continue)):
                return False
            if (
                isinstance(statement, ast.Assert)
                and _literal_truth_value(statement.test) is False
            ):
                return False
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
                if not collect(statement.body):
                    return False
                continue
            if isinstance(statement, ast.If) and not _statements_fall_through(
                [statement]
            ):
                return False
        return True

    collect(tree.body)
    return calls


def _gradio_applies_css(
    tree: ast.Module,
    css_variables: dict[str, SourcePosition],
) -> bool:
    aliases = _module_aliases(tree, "gradio")
    constructors = {"Blocks", "ChatInterface", "Interface", "TabbedInterface"}
    for node in _direct_top_level_calls(tree):
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        import_position = aliases.get(node.func.value.id)
        call_position = _source_position(node)
        if (
            import_position is None
            or import_position >= call_position
            or node.func.attr not in constructors
        ):
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "css"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id in css_variables
                and css_variables[keyword.value.id] < call_position
            ):
                return True
    return False


def _style_expression_parts(
    expression: ast.AST,
    css_variables: dict[str, SourcePosition],
    call_position: SourcePosition,
) -> list[str | None] | None:
    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return [expression.value]
    if (
        isinstance(expression, ast.Name)
        and expression.id in css_variables
        and css_variables[expression.id] < call_position
    ):
        return [None]
    if isinstance(expression, ast.FormattedValue):
        if expression.conversion != -1 or expression.format_spec is not None:
            return None
        return _style_expression_parts(expression.value, css_variables, call_position)
    if isinstance(expression, ast.JoinedStr):
        parts: list[str | None] = []
        for value in expression.values:
            nested = _style_expression_parts(value, css_variables, call_position)
            if nested is None:
                return None
            parts.extend(nested)
        return parts
    if isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        left = _style_expression_parts(expression.left, css_variables, call_position)
        right = _style_expression_parts(expression.right, css_variables, call_position)
        if left is None or right is None:
            return None
        return left + right
    return None


class _StylePlaceholderParser(HTMLParser):
    _INERT_CONTAINERS = frozenset(
        {
            "iframe",
            "noembed",
            "noframes",
            "noscript",
            "object",
            "plaintext",
            "script",
            "template",
            "textarea",
            "title",
            "xmp",
        }
    )
    _FOREIGN_CONTAINERS = frozenset({"math", "svg"})

    def __init__(self, placeholder: str) -> None:
        super().__init__(convert_charrefs=False)
        self._placeholder = placeholder
        self._inert_stack: list[str] = []
        self._foreign_stack: list[str] = []
        self._style_frames: list[list[str]] = []
        self.has_enclosed_placeholder = False
        self.is_malformed = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if self._style_frames and normalized_tag != "style":
            self.is_malformed = True
            return
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
        if normalized_tag != "style":
            return
        if self._style_frames:
            self.is_malformed = True
        values: dict[str, str] = {}
        duplicates: set[str] = set()
        for name, value in attrs:
            key = str(name).casefold()
            if key in values:
                duplicates.add(key)
                continue
            values[key] = "" if value is None else str(value)
        if duplicates & {"disabled", "media", "type"}:
            self.is_malformed = True
        media = values.get("media", "").strip(CSS_WHITESPACE).casefold()
        content_type = values.get("type", "").strip(CSS_WHITESPACE).casefold()
        if "disabled" in values or media not in {"", "all"}:
            self.is_malformed = True
        if content_type not in {"", "text/css"}:
            self.is_malformed = True
        self._style_frames.append([])

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        normalized_tag = tag.casefold()
        if self._style_frames:
            self.is_malformed = True
            return
        if (
            normalized_tag in self._INERT_CONTAINERS
            or normalized_tag in self._FOREIGN_CONTAINERS
            or normalized_tag == "style"
        ):
            self.is_malformed = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if self._style_frames and normalized_tag != "style":
            self.is_malformed = True
            return
        if self._foreign_stack:
            if normalized_tag in self._FOREIGN_CONTAINERS:
                expected = self._foreign_stack[-1]
                if normalized_tag != expected:
                    self.is_malformed = True
                    return
                self._foreign_stack.pop()
            return
        if self._inert_stack:
            if normalized_tag in self._INERT_CONTAINERS:
                expected = self._inert_stack[-1]
                if normalized_tag != expected:
                    self.is_malformed = True
                    return
                self._inert_stack.pop()
            return
        if normalized_tag != "style":
            return
        if not self._style_frames:
            self.is_malformed = True
            return
        content = "".join(self._style_frames.pop()).strip(CSS_WHITESPACE)
        if content == self._placeholder:
            self.has_enclosed_placeholder = True

    def handle_data(self, data: str) -> None:
        if not self._style_frames:
            return
        self._style_frames[-1].append(data)

    def handle_comment(self, data: str) -> None:
        del data
        if self._style_frames:
            self.is_malformed = True

    def handle_entityref(self, name: str) -> None:
        del name
        if self._style_frames:
            self.is_malformed = True

    def handle_charref(self, name: str) -> None:
        del name
        if self._style_frames:
            self.is_malformed = True

    def handle_decl(self, decl: str) -> None:
        del decl
        if self._style_frames:
            self.is_malformed = True

    def handle_pi(self, data: str) -> None:
        del data
        if self._style_frames:
            self.is_malformed = True

    @property
    def has_unclosed_style(self) -> bool:
        return bool(self._style_frames or self._inert_stack or self._foreign_stack)


def _style_expression_uses_css(
    expression: ast.AST,
    css_variables: dict[str, SourcePosition],
    call_position: SourcePosition,
) -> bool:
    parts = _style_expression_parts(expression, css_variables, call_position)
    if parts is None or not any(part is None for part in parts):
        return False
    literal_text = "".join(part for part in parts if part is not None)
    placeholder = "SZL_DECLARED_CSS_PLACEHOLDER"
    while placeholder in literal_text:
        placeholder += "_UNIQUE"
    rendered = "".join(placeholder if part is None else part for part in parts)
    parser = _StylePlaceholderParser(placeholder)
    parser.feed(rendered)
    parser.close()
    return (
        parser.has_enclosed_placeholder
        and not parser.has_unclosed_style
        and not parser.is_malformed
    )


def _streamlit_applies_css(
    tree: ast.Module,
    css_variables: dict[str, SourcePosition],
) -> bool:
    aliases = _module_aliases(tree, "streamlit")
    for node in _direct_top_level_calls(tree):
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        import_position = aliases.get(node.func.value.id)
        call_position = _source_position(node)
        if (
            import_position is None
            or import_position >= call_position
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
            and _style_expression_uses_css(
                node.args[0],
                css_variables,
                call_position,
            )
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
    """Extract exact side-effect imports from the JavaScript module prologue.

    Import-looking JSX text is not JavaScript code, but recognizing all of JSX
    without a JavaScript parser is unsafe.  Static imports and the audit marker
    therefore count only in the leading comment/import prologue, before the
    first executable module token.  This is a deliberately narrow subset of
    valid JavaScript and cannot be reached from JSX text.
    """
    marker = False
    imports: list[str] = []
    cursor = 0
    while cursor < len(app_text):
        if app_text[cursor].isspace():
            cursor += 1
            continue
        if app_text.startswith("//", cursor):
            end = len(app_text)
            for separator in ("\r", "\n"):
                candidate = app_text.find(separator, cursor + 2)
                if candidate >= 0:
                    end = min(end, candidate)
            if app_text[cursor:end].strip() == REACT_MARKER:
                marker = True
            cursor = end
            continue
        if app_text.startswith("/*", cursor):
            end = app_text.find("*/", cursor + 2)
            if end < 0:
                raise ContractError("React frontend binding contains an unclosed comment")
            cursor = end + 2
            continue

        if (
            app_text.startswith("import", cursor)
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
            # Other static imports may precede the governed side-effect import.
            # Consume their statement without interpreting their bindings.
            nesting: list[str] = []
            scan = path_start
            pairs = {"(": ")", "[": "]", "{": "}"}
            while scan < len(app_text):
                if app_text.startswith("//", scan):
                    line_end = min(
                        (
                            position
                            for position in (
                                app_text.find("\r", scan + 2),
                                app_text.find("\n", scan + 2),
                            )
                            if position >= 0
                        ),
                        default=len(app_text),
                    )
                    scan = line_end
                    if not nesting:
                        break
                    continue
                if app_text.startswith("/*", scan):
                    comment_end = app_text.find("*/", scan + 2)
                    if comment_end < 0:
                        raise ContractError(
                            "React frontend binding contains an unclosed comment"
                        )
                    scan = comment_end + 2
                    continue
                character = app_text[scan]
                if character in {"'", '"', "`"}:
                    consumed = _consume_javascript_string(app_text, scan)
                    if consumed is None:
                        raise ContractError(
                            "React frontend binding contains an unsupported string literal"
                        )
                    _, scan = consumed
                    continue
                if character in pairs:
                    nesting.append(pairs[character])
                elif nesting and character == nesting[-1]:
                    nesting.pop()
                elif not nesting and character == ";":
                    scan += 1
                    break
                elif not nesting and character in {"\r", "\n"}:
                    scan += 1
                    break
                scan += 1
            cursor = scan
            continue
        # No comment or import declaration can begin here.  Closing the
        # prologue prevents JSX text later in the module from becoming proof.
        break
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
