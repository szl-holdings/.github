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
CONTROLLED_CSS_PROPERTIES = frozenset(REQUIRED_CSS_DECLARATIONS) | frozenset(
    {
        "animation",
        "animation-duration",
        "scroll-behavior",
        "transition",
        "transition-duration",
    }
)
UNSUPPORTED_LOGICAL_OVERFLOW_PROPERTIES = frozenset(
    {
        "overflow-block",
        "overflow-inline",
    }
)
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
    _INERT_CONTAINERS = frozenset({"template"})
    _INERT_NESTING_CONTAINERS = frozenset({"noscript", "template"})
    _FOREIGN_CONTAINERS = frozenset({"math", "svg"})
    _HTML_VOID_ELEMENTS = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )
    _FOREIGN_BREAKOUT_START_TAGS = frozenset(
        {
            "b",
            "big",
            "blockquote",
            "body",
            "br",
            "center",
            "code",
            "dd",
            "div",
            "dl",
            "dt",
            "em",
            "embed",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "head",
            "hr",
            "i",
            "img",
            "li",
            "listing",
            "menu",
            "meta",
            "nobr",
            "ol",
            "p",
            "pre",
            "ruby",
            "s",
            "small",
            "span",
            "strong",
            "strike",
            "sub",
            "sup",
            "table",
            "tt",
            "u",
            "ul",
            "var",
        }
    )
    _FOREIGN_BREAKOUT_END_TAGS = frozenset({"br", "p"})
    _FOREIGN_BREAKOUT_FONT_ATTRIBUTES = frozenset({"color", "face", "size"})
    _VALID_BUILTIN_SHADOW_HOST_NAMES = frozenset(
        {
            "article",
            "aside",
            "blockquote",
            "body",
            "div",
            "footer",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "header",
            "main",
            "nav",
            "p",
            "section",
            "span",
        }
    )
    _RESERVED_CUSTOM_ELEMENT_NAMES = frozenset(
        {
            "annotation-xml",
            "color-profile",
            "font-face",
            "font-face-format",
            "font-face-name",
            "font-face-src",
            "font-face-uri",
            "missing-glyph",
        }
    )
    _SVG_HTML_INTEGRATION_POINTS = frozenset({"desc", "foreignobject", "title"})
    _MATHML_TEXT_INTEGRATION_POINTS = frozenset(
        {"mi", "mn", "mo", "ms", "mtext"}
    )
    _MATHML_FOREIGN_EXCEPTIONS = frozenset({"malignmark", "mglyph"})
    _MATHML_HTML_ENCODINGS = frozenset(
        {"application/xhtml+xml", "text/html"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_viewport = False
        self.viewport_contents: list[str] = []
        self.has_base = False
        self.has_author_style = False
        self.author_stylesheet_links: list[dict[str, str]] = []
        self.stylesheet_links: list[dict[str, str]] = []
        self._inert_stack: list[str] = []
        self._html_element_stack: list[str] = []
        self._foreign_tree_stack: list[tuple[str, str, str | None]] = []

    @property
    def has_unclosed_inert_container(self) -> bool:
        return bool(self._inert_stack)

    @property
    def has_unclosed_foreign_container(self) -> bool:
        return bool(self._foreign_tree_stack)

    @staticmethod
    def _has_author_style(
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> bool:
        return tag == "style" or any(
            str(name).casefold() == "style" for name, _ in attrs
        )

    @classmethod
    def _is_valid_custom_element_name(cls, name: str) -> bool:
        if (
            not name
            or not ("a" <= name[0] <= "z")
            or "-" not in name
            or name in cls._RESERVED_CUSTOM_ELEMENT_NAMES
        ):
            return False
        for character in name[1:]:
            codepoint = ord(character)
            if (
                character in {"-", ".", "_"}
                or "0" <= character <= "9"
                or "a" <= character <= "z"
                or codepoint == 0x00B7
                or 0x00C0 <= codepoint <= 0x00D6
                or 0x00D8 <= codepoint <= 0x00F6
                or 0x00F8 <= codepoint <= 0x037D
                or 0x037F <= codepoint <= 0x1FFF
                or 0x200C <= codepoint <= 0x200D
                or 0x203F <= codepoint <= 0x2040
                or 0x2070 <= codepoint <= 0x218F
                or 0x2C00 <= codepoint <= 0x2FEF
                or 0x3001 <= codepoint <= 0xD7FF
                or 0xF900 <= codepoint <= 0xFDCF
                or 0xFDF0 <= codepoint <= 0xFFFD
                or 0x10000 <= codepoint <= 0xEFFFF
            ):
                continue
            return False
        return True

    @classmethod
    def _is_valid_shadow_host_name(cls, name: str | None) -> bool:
        return name is not None and (
            name in cls._VALID_BUILTIN_SHADOW_HOST_NAMES
            or cls._is_valid_custom_element_name(name)
        )

    @staticmethod
    def _shadowroot_mode(
        attrs: list[tuple[str, str | None]],
    ) -> str | None:
        for name, value in attrs:
            if str(name).casefold() != "shadowrootmode":
                continue
            mode = "" if value is None else str(value).casefold()
            if mode in {"closed", "open"}:
                return mode
            return None
        return None

    def _current_html_parent_name(self) -> str | None:
        if self._foreign_tree_stack:
            tag, namespace, _ = self._foreign_tree_stack[-1]
            return tag if namespace == "html" else None
        if self._html_element_stack:
            return self._html_element_stack[-1]
        return None

    def _has_html_noscript_ancestor(self) -> bool:
        if "noscript" in self._html_element_stack:
            return True
        return any(
            tag == "noscript" and namespace == "html"
            for tag, namespace, _ in self._foreign_tree_stack
        )

    @classmethod
    def _is_foreign_breakout_start_tag(
        cls,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> bool:
        if tag in cls._FOREIGN_BREAKOUT_START_TAGS:
            return True
        if tag != "font":
            return False
        return any(
            str(name).casefold() in cls._FOREIGN_BREAKOUT_FONT_ATTRIBUTES
            for name, _ in attrs
        )



    @classmethod
    def _integration_kind(
        cls,
        namespace: str,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> str | None:
        if namespace == "svg":
            if tag in cls._SVG_HTML_INTEGRATION_POINTS:
                return "html"
            return None
        if namespace != "math":
            return None
        if tag in cls._MATHML_TEXT_INTEGRATION_POINTS:
            return "math-text"
        if tag != "annotation-xml":
            return None
        encodings = [
            "" if value is None else str(value)
            for name, value in attrs
            if str(name).casefold() == "encoding"
        ]
        if (
            len(encodings) == 1
            and encodings[0].casefold() in cls._MATHML_HTML_ENCODINGS
        ):
            return "html"
        return None

    def _namespace_for_start_tag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> str:
        if not self._foreign_tree_stack:
            if tag in self._FOREIGN_CONTAINERS:
                return tag
            return "html"
        (
            current_tag,
            current_namespace,
            integration_kind,
        ) = self._foreign_tree_stack[-1]
        process_as_html = (
            current_namespace == "html"
            or integration_kind == "html"
            or (
                integration_kind == "math-text"
                and tag not in self._MATHML_FOREIGN_EXCEPTIONS
            )
            or (
                current_namespace == "math"
                and current_tag == "annotation-xml"
                and tag == "svg"
            )
        )
        if process_as_html:
            if tag in self._FOREIGN_CONTAINERS:
                return tag
            return "html"
        if self._is_foreign_breakout_start_tag(tag, attrs):
            raise ContractError(
                "Static application contains a foreign-content breakout parse error "
                "that can expose unaudited author styles"
            )
        return current_namespace

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if self._inert_stack:
            if normalized_tag in self._INERT_NESTING_CONTAINERS:
                self._inert_stack.append(normalized_tag)
            return

        namespace = self._namespace_for_start_tag(normalized_tag, attrs)
        if (
            namespace == "html"
            and normalized_tag in self._INERT_CONTAINERS
        ):
            if (
                normalized_tag == "template"
                and self._shadowroot_mode(attrs) is not None
                and self._is_valid_shadow_host_name(
                    self._current_html_parent_name()
                )
            ):
                raise ContractError(
                    "Static application may not use a declarative shadow root template"
                )
            self._inert_stack.append(normalized_tag)
            return

        if self._has_author_style(normalized_tag, attrs):
            self.has_author_style = True
        if namespace == "html":
            self._record(tag, attrs)

        if not self._foreign_tree_stack and namespace == "html":
            if normalized_tag not in self._HTML_VOID_ELEMENTS:
                self._html_element_stack.append(normalized_tag)
            return
        if (
            namespace == "html"
            and normalized_tag in self._HTML_VOID_ELEMENTS
        ):
            return
        self._foreign_tree_stack.append(
            (
                normalized_tag,
                namespace,
                self._integration_kind(namespace, normalized_tag, attrs),
            )
        )

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.casefold()
        if self._inert_stack:
            return

        namespace = self._namespace_for_start_tag(normalized_tag, attrs)
        if (
            namespace == "html"
            and normalized_tag in self._INERT_CONTAINERS
        ):
            raise ContractError(
                f"Static application contains self-closing <{normalized_tag}>"
            )
        if self._has_author_style(normalized_tag, attrs):
            self.has_author_style = True
        if namespace == "html":
            self._record(tag, attrs)
            if normalized_tag not in self._HTML_VOID_ELEMENTS:
                if self._foreign_tree_stack:
                    self._foreign_tree_stack.append(
                        (
                            normalized_tag,
                            namespace,
                            self._integration_kind(
                                namespace,
                                normalized_tag,
                                attrs,
                            ),
                        )
                    )
                else:
                    self._html_element_stack.append(normalized_tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.casefold()
        if self._inert_stack:
            if normalized_tag not in self._INERT_NESTING_CONTAINERS:
                return
            expected = self._inert_stack[-1]
            if normalized_tag != expected:
                raise ContractError(
                    "Static application contains mismatched inert containers: "
                    f"expected </{expected}>, received </{normalized_tag}>"
                )
            self._inert_stack.pop()
            return

        if not self._foreign_tree_stack:
            for index in range(len(self._html_element_stack) - 1, -1, -1):
                if self._html_element_stack[index] == normalized_tag:
                    del self._html_element_stack[index:]
                    break
            return
        if (
            self._foreign_tree_stack[-1][1] != "html"
            and normalized_tag in self._FOREIGN_BREAKOUT_END_TAGS
        ):
            raise ContractError(
                "Static application contains a foreign-content breakout parse error "
                "that can expose unaudited author styles"
            )
        expected = self._foreign_tree_stack[-1][0]
        if normalized_tag != expected:
            raise ContractError(
                "Static application contains mismatched foreign containers "
                "or HTML integration descendants: "
                f"expected </{expected}>, received </{normalized_tag}>"
            )
        self._foreign_tree_stack.pop()
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
        if "style" in values or normalized_tag == "style":
            self.has_author_style = True
        if normalized_tag == "base":
            self.has_base = True
            return
        if (
            normalized_tag == "meta"
            and values.get("name", "")
            .strip(HTML_ASCII_WHITESPACE)
            .casefold()
            == "viewport"
        ):
            ambiguous_viewport = sorted(duplicates & {"name", "content"})
            if ambiguous_viewport:
                raise ContractError(
                    "Static viewport metadata contains duplicate controlled attributes: "
                    + ", ".join(ambiguous_viewport)
                )
            self.has_viewport = True
            self.viewport_contents.append(values.get("content", ""))
        if normalized_tag != "link":
            return
        security_attributes = {
            "rel",
            "href",
            "integrity",
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
        if "stylesheet" not in rel_tokens:
            return
        self.author_stylesheet_links.append(values)
        if "alternate" in rel_tokens:
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
        if self._has_html_noscript_ancestor():
            return
        self.stylesheet_links.append(values)


def _valid_static_viewport_content(content: str) -> bool:
    directives: dict[str, str] = {}
    for raw_directive in content.split(","):
        directive = raw_directive.strip(HTML_ASCII_WHITESPACE)
        match = re.fullmatch(
            r"([A-Za-z][A-Za-z0-9-]*)[ \t\n\f\r]*=[ \t\n\f\r]*([^ \t\n\f\r,]+)",
            directive,
        )
        if match is None:
            return False
        name = match.group(1).casefold()
        if name in directives:
            return False
        directives[name] = match.group(2).casefold()
    return directives.get("width") == "device-width"


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
    key_value_pattern = re.compile(
        r'''^([A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'''
        r"""'(?:[^']|'')*')\s*:\s*(.*?)\s*$"""
    )
    for line in text[4:end].splitlines():
        match = key_value_pattern.match(line)
        if not match:
            stripped = line.lstrip()
            if (
                line == stripped
                and ":" in line
                and not stripped.startswith(("#", "-"))
            ):
                raise ContractError(
                    "README.md contains unsupported top-level "
                    "front-matter mapping syntax"
                )
            continue
        raw_key = match.group(1)
        if raw_key.startswith('"'):
            if "\\" in raw_key[1:-1]:
                raise ContractError(
                    "README.md contains unsupported escaped front-matter key syntax"
                )
            key = raw_key[1:-1]
        elif raw_key.startswith("'"):
            key = raw_key[1:-1].replace("''", "'")
        else:
            key = raw_key
        if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ContractError(
                "README.md contains unsupported front-matter key syntax"
            )
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
            statement = css_text[start:cursor].strip(CSS_WHITESPACE)
            if statement:
                raise ContractError(
                    "universal CSS may not contain top-level semicolon statements "
                    "such as @import"
                )
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


def _decode_css_identifier(identifier: str) -> str:
    decoded: list[str] = []
    cursor = 0
    hexadecimal = "0123456789abcdefABCDEF"
    while cursor < len(identifier):
        character = identifier[cursor]
        if character != "\\":
            decoded.append(character)
            cursor += 1
            continue

        cursor += 1
        if cursor >= len(identifier) or identifier[cursor] in {"\r", "\n", "\f"}:
            raise ContractError(
                "universal CSS contains an invalid property-name escape"
            )
        if identifier[cursor] in hexadecimal:
            start = cursor
            while (
                cursor < len(identifier)
                and cursor - start < 6
                and identifier[cursor] in hexadecimal
            ):
                cursor += 1
            code_point = int(identifier[start:cursor], 16)
            if (
                code_point == 0
                or code_point > 0x10FFFF
                or 0xD800 <= code_point <= 0xDFFF
            ):
                raise ContractError(
                    "universal CSS contains an invalid property-name escape"
                )
            decoded.append(chr(code_point))
            if cursor < len(identifier) and identifier[cursor] in CSS_WHITESPACE:
                if (
                    identifier[cursor] == "\r"
                    and cursor + 1 < len(identifier)
                    and identifier[cursor + 1] == "\n"
                ):
                    cursor += 2
                else:
                    cursor += 1
            continue

        if identifier[cursor] == "\0":
            raise ContractError(
                "universal CSS contains an invalid property-name escape"
            )
        decoded.append(identifier[cursor])
        cursor += 1
    return "".join(decoded)


def _split_css_component_level(
    text: str,
    delimiter: str,
    *,
    maxsplit: int | None = None,
) -> list[str]:
    if len(delimiter) != 1:
        raise ValueError("CSS component delimiter must be one character")
    pairs = {"(": ")", "[": "]"}
    closers = set(pairs.values())
    stack: list[str] = []
    parts: list[str] = []
    start = 0
    cursor = 0
    splits = 0
    while cursor < len(text):
        character = text[cursor]
        if character == "\\":
            if cursor + 1 >= len(text):
                raise ContractError(
                    "universal CSS contains an invalid component-value escape"
                )
            cursor += 2
            continue
        if character in pairs:
            stack.append(pairs[character])
        elif character in closers:
            if not stack or character != stack[-1]:
                raise ContractError(
                    "universal CSS contains mismatched component-value nesting"
                )
            stack.pop()
        elif (
            character == delimiter
            and not stack
            and (maxsplit is None or splits < maxsplit)
        ):
            parts.append(text[start:cursor])
            start = cursor + 1
            splits += 1
        cursor += 1
    if stack:
        raise ContractError("universal CSS contains an unclosed component value")
    parts.append(text[start:])
    return parts


def _split_css_important_annotation(value: str) -> tuple[str, bool]:
    """Return a declaration value and whether its final annotation is important."""
    normalized = value.rstrip(CSS_WHITESPACE)
    bang_index = normalized.rfind("!")
    if bang_index == -1:
        return normalized, False
    annotation = normalized[bang_index + 1 :].strip(CSS_WHITESPACE)
    if not annotation:
        return normalized, False
    if _decode_css_identifier(annotation).casefold() != "important":
        return normalized, False
    return normalized[:bang_index].rstrip(CSS_WHITESPACE), True


OVERFLOW_AXIS_VALUES = frozenset({"visible", "hidden", "clip", "scroll", "auto"})
CSS_WIDE_VALUES = frozenset(
    {"inherit", "initial", "revert", "revert-layer", "unset"}
)


def _overflow_x_from_shorthand(value: str) -> str:
    """Validate overflow shorthand syntax and return its computed x-axis value."""
    components = value.split(" ")
    if len(components) == 1:
        component = components[0]
        if component in OVERFLOW_AXIS_VALUES or component in CSS_WIDE_VALUES:
            return component
    elif len(components) == 2 and all(
        component in OVERFLOW_AXIS_VALUES for component in components
    ):
        overflow_x, overflow_y = components
        if overflow_y not in {"visible", "clip"}:
            if overflow_x == "visible":
                return "auto"
            if overflow_x == "clip":
                return "hidden"
        return overflow_x
    raise ContractError(
        "universal CSS contains an unsupported or invalid overflow shorthand: "
        f"{value}"
    )


def _css_declarations(rule_body: str) -> list[tuple[str, str, bool]]:
    """Parse declarations at the current rule level, rejecting nested rules."""
    flattened: list[str] = []
    brace_depth = 0
    saw_nested_rule = False
    for character in rule_body:
        if character == "{":
            saw_nested_rule = True
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
    if saw_nested_rule:
        raise ContractError("universal CSS contains an unsupported nested rule")

    declarations: list[tuple[str, str, bool]] = []
    for declaration in _split_css_component_level("".join(flattened), ";"):
        components = _split_css_component_level(declaration, ":", maxsplit=1)
        if len(components) != 2:
            continue
        property_name, value = components
        normalized_property = _decode_css_identifier(
            property_name.strip(CSS_WHITESPACE)
        )
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
        normalized_value, important = _split_css_important_annotation(
            normalized_value
        )
        if not normalized_property or not normalized_value:
            continue
        if normalized_property in UNSUPPORTED_LOGICAL_OVERFLOW_PROPERTIES:
            raise ContractError(
                "universal CSS may not declare logical overflow properties: "
                f"{normalized_property}"
            )
        declarations.append((normalized_property, normalized_value, important))
        if normalized_property == "overflow":
            overflow_x = _overflow_x_from_shorthand(normalized_value)
            declarations.append(("overflow-x", overflow_x, important))
        elif normalized_property == "all":
            reset_value = f"__all_reset__:{normalized_value}"
            for controlled_property in (
                "animation",
                "animation-duration",
                "overflow-wrap",
                "overflow-x",
                "scroll-behavior",
                "transition",
                "transition-duration",
            ):
                declarations.append(
                    (controlled_property, reset_value, important)
                )
        elif normalized_property in {"animation", "transition"}:
            duration_property = f"{normalized_property}-duration"
            duration_value = (
                "0s"
                if normalized_value == "none"
                else f"__{normalized_property}_reset__:{normalized_value}"
            )
            declarations.append((duration_property, duration_value, important))
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


NON_CASCADE_BLOCK_AT_RULES = {"font-face"}


def _require_non_cascade_at_rule(prelude: str) -> None:
    match = re.match(
        r"@([A-Za-z_-][A-Za-z0-9_-]*)",
        prelude.strip(CSS_WHITESPACE),
    )
    if not match:
        raise ContractError("universal CSS contains an unsupported at-rule block")
    name = match.group(1).casefold()
    if name not in NON_CASCADE_BLOCK_AT_RULES:
        raise ContractError(
            "universal CSS is missing required active tokens; unsupported conditional or at-rule block: "
            f"@{name}"
        )


CSSCascadeEntry = tuple[str, str, str, bool, int]
CSSCascadeWinner = tuple[str, bool, tuple[int, int, int], int]

AUDITED_SELECTOR_TARGETS = {
    ":root": frozenset({"root"}),
    "html": frozenset({"root"}),
    "body": frozenset({"body"}),
    "*": frozenset({"root", "body", "element"}),
    "*::before": frozenset({"before"}),
    "*::after": frozenset({"after"}),
}
AUDITED_SELECTOR_SPECIFICITY = {
    ":root": (0, 1, 0),
    "html": (0, 0, 1),
    "body": (0, 0, 1),
    "*": (0, 0, 0),
    "*::before": (0, 0, 1),
    "*::after": (0, 0, 1),
}


def _cascade_winners(
    declarations: list[CSSCascadeEntry],
) -> dict[tuple[str, str], CSSCascadeWinner]:
    """Resolve audited author declarations by importance, specificity, and order."""
    winners: dict[tuple[str, str], CSSCascadeWinner] = {}
    for selector, property_name, value, important, source_order in declarations:
        specificity = AUDITED_SELECTOR_SPECIFICITY[selector]
        priority = (1 if important else 0, specificity, source_order)
        for target in AUDITED_SELECTOR_TARGETS[selector]:
            key = (target, property_name)
            previous = winners.get(key)
            if previous is None:
                winners[key] = (value, important, specificity, source_order)
                continue
            previous_priority = (
                1 if previous[1] else 0,
                previous[2],
                previous[3],
            )
            if priority >= previous_priority:
                winners[key] = (value, important, specificity, source_order)
    return winners


def _effective_inherited_value(
    winners: dict[tuple[str, str], CSSCascadeWinner],
    property_name: str,
) -> str | None:
    """Resolve the audited generic-element value through root/body inheritance."""
    for target in ("element", "body", "root"):
        winner = winners.get((target, property_name))
        if winner is not None:
            return winner[0]
    return None


def _has_required_css_control(
    winners: dict[tuple[str, str], CSSCascadeWinner],
    property_name: str,
    value: str,
) -> bool:
    if property_name in {"--szl-touch-target", "overflow-wrap"}:
        return _effective_inherited_value(winners, property_name) == value
    if property_name == "overflow-x":
        return all(
            (winner := winners.get((target, property_name))) is not None
            and winner[0] == value
            for target in ("root", "body")
        )
    return False


def _has_reduced_motion_control(declarations: list[CSSCascadeEntry]) -> bool:
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
    winners = _cascade_winners(declarations)
    required_targets = {"root", "body", "element", "before", "after"}
    return all(
        any(
            candidate_target == target and (property_name, winner[0]) in accepted
            for (candidate_target, property_name), winner in winners.items()
        )
        for target in required_targets
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


def _reject_unaudited_controlled_declarations(
    declarations: list[tuple[str, str, bool]],
) -> None:
    controlled = sorted(
        {
            property_name
            for property_name, _, _ in declarations
            if property_name in CONTROLLED_CSS_PROPERTIES
        }
    )
    if controlled:
        raise ContractError(
            "universal CSS is missing required active tokens; contains controlled declarations on an unaudited "
            f"selector: {', '.join(controlled)}"
        )


def validate_css(css_text: str) -> None:
    active_css = _strip_css_inert_text(css_text)
    active_declarations: list[CSSCascadeEntry] = []
    media_declarations: dict[str, list[CSSCascadeEntry]] = {
        query: [] for query in REQUIRED_MEDIA_QUERIES
    }
    source_order = 0

    def append_declarations(
        cascade: list[CSSCascadeEntry],
        selectors: set[str],
        declarations: list[tuple[str, str, bool]],
    ) -> None:
        nonlocal source_order
        for property_name, value, important in declarations:
            for selector in selectors:
                cascade.append(
                    (selector, property_name, value, important, source_order)
                )
            source_order += 1

    for prelude, body in _css_rule_blocks(active_css):
        if not prelude.lstrip(CSS_WHITESPACE).startswith("@"):
            declarations = _css_declarations(body)
            selectors = _guaranteed_active_selectors(prelude)
            if not selectors:
                _reject_unaudited_controlled_declarations(declarations)
                continue
            append_declarations(
                active_declarations,
                selectors,
                declarations,
            )
            continue
        query = _media_query(prelude)
        if query not in REQUIRED_MEDIA_QUERIES:
            _require_non_cascade_at_rule(prelude)
            continue
        for nested_prelude, nested_body in _css_rule_blocks(body):
            if nested_prelude.lstrip(CSS_WHITESPACE).startswith("@"):
                _require_non_cascade_at_rule(nested_prelude)
                continue
            declarations = _css_declarations(nested_body)
            selectors = _guaranteed_active_selectors(nested_prelude)
            if not selectors:
                _reject_unaudited_controlled_declarations(declarations)
                continue
            append_declarations(
                media_declarations[query],
                selectors,
                declarations,
            )

    active_winners = _cascade_winners(active_declarations)
    observed_media = {
        query
        for query, declarations in media_declarations.items()
        if declarations
        and (
            query != "(prefers-reduced-motion:reduce)"
            or _has_reduced_motion_control(active_declarations + declarations)
        )
    }

    missing = [
        f"{name}: {value}"
        for name, value in REQUIRED_CSS_DECLARATIONS.items()
        if not _has_required_css_control(active_winners, name, value)
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


def _loop_is_fallthrough_barrier(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.While):
        return _literal_truth_value(statement.test) is not False
    return isinstance(statement, (ast.For, ast.AsyncFor))


TRY_STATEMENT_TYPES = (ast.Try, getattr(ast, "TryStar", ast.Try))
FUNCTION_DEFINITION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _function_definition_is_plain_inert(
    statement: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    arguments = statement.args
    parameters = [
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
    ]
    if arguments.vararg is not None:
        parameters.append(arguments.vararg)
    if arguments.kwarg is not None:
        parameters.append(arguments.kwarg)

    return (
        not statement.decorator_list
        and not arguments.defaults
        and all(default is None for default in arguments.kw_defaults)
        and statement.returns is None
        and all(parameter.annotation is None for parameter in parameters)
    )


def _lambda_definition_is_plain_inert(expression: ast.Lambda) -> bool:
    arguments = expression.args
    return not arguments.defaults and all(
        default is None for default in arguments.kw_defaults
    )


def _try_statement_falls_through(statement: ast.Try) -> bool:
    """Fail closed on a top-level try before a claimed framework binding."""
    # Reachability depends on runtime name resolution plus evaluation of the
    # try body, exception constructor, cause, handler types, and finally body.
    # A partial evaluator can turn an actually unreachable binding green, so
    # this contract requires the binding to precede any top-level try.
    return False


def _statements_fall_through(statements: list[ast.stmt]) -> bool:
    for statement in statements:
        if isinstance(statement, FUNCTION_DEFINITION_TYPES):
            if not _function_definition_is_plain_inert(statement):
                return False
            continue
        if isinstance(statement, ast.ClassDef):
            return False
        lambda_expression: ast.AST | None = None
        if isinstance(statement, ast.Assign):
            lambda_expression = statement.value
        elif isinstance(statement, ast.AnnAssign):
            lambda_expression = statement.value
        if (
            isinstance(lambda_expression, ast.Lambda)
            and not _lambda_definition_is_plain_inert(lambda_expression)
        ):
            return False
        if isinstance(statement, (ast.Raise, ast.Return, ast.Break, ast.Continue)):
            return False
        if _loop_is_fallthrough_barrier(statement):
            return False
        if (
            isinstance(statement, ast.Assert)
            and _literal_truth_value(statement.test) is False
        ):
            return False
        if isinstance(statement, TRY_STATEMENT_TYPES):
            if not _try_statement_falls_through(statement):
                return False
            continue
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
            branch_falls_through = body_falls_through and else_falls_through
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
    local_function_names: set[str] = set()

    def collect(statements: list[ast.stmt]) -> bool:
        """Collect calls until control can no longer reach the next statement."""
        for statement in statements:
            if isinstance(statement, FUNCTION_DEFINITION_TYPES):
                if not _function_definition_is_plain_inert(statement):
                    return False
                local_function_names.add(statement.name)
                continue
            if isinstance(statement, ast.ClassDef):
                return False
            if isinstance(statement, (ast.Raise, ast.Return, ast.Break, ast.Continue)):
                return False
            if _loop_is_fallthrough_barrier(statement):
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
            if isinstance(expression, ast.Lambda):
                if not _lambda_definition_is_plain_inert(expression):
                    return False
                continue
            if isinstance(expression, ast.Call):
                if isinstance(expression.func, ast.Lambda):
                    return False
                if (
                    isinstance(expression.func, ast.Name)
                    and expression.func.id in local_function_names
                ):
                    return False
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
            if isinstance(
                statement,
                (ast.If,) + TRY_STATEMENT_TYPES,
            ) and not _statements_fall_through([statement]):
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
        if any(keyword.arg is None for keyword in node.keywords):
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
            or len(node.args) != 1
        ):
            continue
        if any(keyword.arg is None for keyword in node.keywords):
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
    if re.search(r"%(?:2f|5c)", parsed.path, flags=re.IGNORECASE):
        raise ContractError(
            "static universal stylesheet href may not contain encoded path separators"
        )
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

        if not parser.viewport_contents:
            raise ContractError("Static viewport metadata is absent")
        if len(parser.viewport_contents) != 1:
            raise ContractError(
                "Static application must contain exactly one viewport meta element"
            )
        if not _valid_static_viewport_content(parser.viewport_contents[0]):
            raise ContractError(
                "Static viewport metadata must contain one supported width=device-width directive"
            )
        if parser.has_base:
            raise ContractError(
                "Static application may not override repository-local URL resolution with <base>"
            )
        if parser.has_author_style:
            raise ContractError(
                "Static application contains unaudited author styles; use only the universal stylesheet link"
            )
        if len(parser.author_stylesheet_links) != 1:
            raise ContractError(
                "Static universal CSS requires exactly one stylesheet <link>; additional author styles are not allowed"
            )
        expected_css = posixpath.normpath(css_file)
        for link in parser.stylesheet_links:
            if "integrity" in link:
                raise ContractError(
                    "Static universal stylesheet link may not use integrity metadata"
                )
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
