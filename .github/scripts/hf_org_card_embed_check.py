#!/usr/bin/env python3
"""Fail-closed host-isolation checks for the Hugging Face organization card."""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


ROOT_ID = "szl-hf-org-card"
ROOT_SELECTOR = f"#{ROOT_ID}"
CLASS_PREFIX = "szl-hf-"
BODY_MARKER = "company-front-door"
CANONICAL_ASSET_URL = (
    "https://szlholdings-readme.static.hf.space/"
    "assets/evidence-lattice-v2.webp"
)
CANONICAL_DEPLOYMENT_URL = (
    "https://szlholdings-readme.static.hf.space/deployment.json"
)
VOID_ELEMENTS = {
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
CSS_CLASS = re.compile(r"(?<![A-Za-z0-9_-])\.([A-Za-z_][A-Za-z0-9_-]*)")
CSS_ID = re.compile(r"(?<![A-Za-z0-9_-])#([A-Za-z_][A-Za-z0-9_-]*)")
CSS_COLOR = re.compile(r"^[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?$|^[0-9a-fA-F]{4}(?:[0-9a-fA-F]{4})?$")
CSS_EXTERNAL = re.compile(r"(?i)(?:@import\b|url\s*\()")
ROOT_OVERFLOW_MASK = re.compile(
    rf"(?is)^\s*{re.escape(ROOT_SELECTOR)}(?:\[[^]]+\])?\s*$"
)


class OrgCardParser(HTMLParser):
    """Collect structural facts while tracking the isolated body subtree."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root_count = 0
        self.root_embed_safe = False
        self.body_marker = ""
        self.h1_count = 0
        self.main_count = 0
        self.class_tokens: set[str] = set()
        self.ids: list[str] = []
        self.aria_labelledby: list[str] = []
        self.hrefs: list[str] = []
        self.images: list[dict[str, str]] = []
        self.styles: list[str] = []
        self.inline_style_count = 0
        self.forbidden_elements: list[str] = []
        self.outside_root: list[str] = []
        self._in_body = False
        self._root_depth = 0
        self.elements: list[tuple[str, dict[str, str], int | None]] = []
        self._stack: list[tuple[str, bool, int | None]] = []
        self._in_style = False
        self._style_parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = {key: str(value or "") for key, value in attrs}
        is_root = values.get("id") == ROOT_ID
        inside_root = self._root_depth > 0 or is_root
        element_index: int | None = None
        if inside_root:
            parent_index = next(
                (
                    opened_index
                    for _, _, opened_index in reversed(self._stack)
                    if opened_index is not None
                ),
                None,
            )
            element_index = len(self.elements)
            self.elements.append((tag, values, parent_index))

        if tag == "body":
            self._in_body = True
            self.body_marker = values.get("data-szl-surface", "")
        elif self._in_body and not inside_root:
            self.outside_root.append(tag)

        if is_root:
            self.root_count += 1
            self.root_embed_safe = (
                values.get("data-szl-embed-safe", "").casefold() == "true"
            )

        classes = values.get("class", "").split()
        self.class_tokens.update(classes)
        if values.get("id"):
            self.ids.append(values["id"])
        if "aria-labelledby" in values:
            self.aria_labelledby.append(values["aria-labelledby"])
        if values.get("style"):
            self.inline_style_count += 1

        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"])
        if tag == "img":
            self.images.append(values)
        if tag in {"script", "link", "base"}:
            self.forbidden_elements.append(tag)
        if tag == "h1" and inside_root:
            self.h1_count += 1
        if tag == "main" and inside_root:
            self.main_count += 1
        if tag == "style":
            self._in_style = True
            self._style_parts = []

        if tag not in VOID_ELEMENTS:
            self._stack.append((tag, inside_root, element_index))
            if inside_root:
                self._root_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._in_style:
            self.styles.append("".join(self._style_parts))
            self._style_parts = []
            self._in_style = False
        if tag == "body":
            self._in_body = False
        if self._stack:
            opened_tag, inside_root, _ = self._stack.pop()
            if opened_tag != tag:
                self.outside_root.append(f"mismatched:{opened_tag}/{tag}")
            if inside_root:
                self._root_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_parts.append(data)


def _skip_css_string(source: str, position: int) -> int:
    quote = source[position]
    position += 1
    while position < len(source):
        if source[position] == "\\":
            position += 2
        elif source[position] == quote:
            return position + 1
        else:
            position += 1
    raise ValueError("unterminated CSS string")


def css_blocks(source: str) -> list[tuple[str, str]]:
    """Return top-level CSS block preludes and bodies, rejecting bad balance."""

    cleaned = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    blocks: list[tuple[str, str]] = []
    position = 0
    while position < len(cleaned):
        while position < len(cleaned) and (
            cleaned[position].isspace() or cleaned[position] == ";"
        ):
            position += 1
        if position >= len(cleaned):
            break
        start = position
        while position < len(cleaned) and cleaned[position] not in "{;":
            if cleaned[position] in {'"', "'"}:
                position = _skip_css_string(cleaned, position)
            else:
                position += 1
        if position >= len(cleaned):
            if cleaned[start:].strip():
                raise ValueError("CSS statement lacks a terminator")
            break
        if cleaned[position] == ";":
            statement = cleaned[start : position + 1].strip()
            if statement:
                blocks.append((statement, ""))
            position += 1
            continue
        prelude = cleaned[start:position].strip()
        depth = 1
        body_start = position + 1
        position = body_start
        while position < len(cleaned) and depth:
            if cleaned[position] in {'"', "'"}:
                position = _skip_css_string(cleaned, position)
            elif cleaned[position] == "{":
                depth += 1
                position += 1
            elif cleaned[position] == "}":
                depth -= 1
                position += 1
            else:
                position += 1
        if depth:
            raise ValueError(f"unclosed CSS block: {prelude}")
        blocks.append((prelude, cleaned[body_start : position - 1]))
    return blocks


def split_selector_members(value: str) -> list[str]:
    members: list[str] = []
    start = 0
    parentheses = 0
    brackets = 0
    quote = ""
    position = 0
    while position < len(value):
        char = value[position]
        if quote:
            if char == "\\":
                position += 2
                continue
            if char == quote:
                quote = ""
        elif char in {'"', "'"}:
            quote = char
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "," and not parentheses and not brackets:
            members.append(value[start:position].strip())
            start = position + 1
        position += 1
    members.append(value[start:].strip())
    return members


def selector_failures(source: str) -> list[str]:
    failures: list[str] = []
    selector_count = 0

    def inspect(block_source: str) -> None:
        nonlocal selector_count
        for prelude, body in css_blocks(block_source):
            if prelude.startswith("@"):
                keyword = prelude.split(None, 1)[0].casefold()
                if keyword not in {"@media", "@supports", "@layer"}:
                    failures.append(f"unsupported CSS at-rule: {keyword}")
                elif body:
                    inspect(body)
                continue
            for selector in split_selector_members(prelude):
                selector_count += 1
                boundary = selector[len(ROOT_SELECTOR) : len(ROOT_SELECTOR) + 1]
                if not selector.startswith(ROOT_SELECTOR) or (
                    boundary and (boundary.isalnum() or boundary in "_-")
                ):
                    failures.append(f"unrooted CSS selector: {selector}")
                if ":root" in selector or re.search(r"(?<![-\w])(html|body)(?![-\w])", selector):
                    failures.append(f"host-level CSS selector: {selector}")
            try:
                nested_blocks = css_blocks(body)
            except ValueError as exc:
                failures.append(f"nested CSS parse failed: {exc}")
                nested_blocks = []
            if any(nested_body for _, nested_body in nested_blocks):
                failures.append(f"native CSS nesting is unsupported: {prelude}")
            if ROOT_OVERFLOW_MASK.fullmatch(prelude) and re.search(
                r"(?i)\boverflow(?:-[xy])?\s*:\s*(?:hidden|clip)\b", body
            ):
                failures.append("org-card root must not mask overflow")

    try:
        inspect(source)
    except ValueError as exc:
        failures.append(f"CSS parse failed: {exc}")
    if not selector_count:
        failures.append("no CSS selectors were evaluated")
    return failures


def _safe_href(value: str) -> bool:
    if value.startswith("#"):
        return len(value) > 1 and " " not in value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
    )


def validate_document(document: str) -> list[str]:
    failures: list[str] = []
    parser = OrgCardParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception as exc:
        return [f"HTML parse failed: {type(exc).__name__}: {exc}"]

    if parser.root_count != 1:
        failures.append(f"expected one isolated root, observed {parser.root_count}")
    if not parser.root_embed_safe:
        failures.append("isolated root must declare data-szl-embed-safe=true")
    if parser.body_marker != BODY_MARKER:
        failures.append(f"body marker must be {BODY_MARKER}")
    if parser.outside_root:
        failures.append(f"body content escaped the isolated root: {parser.outside_root}")
    if parser.h1_count != 1 or parser.main_count != 1:
        failures.append("isolated card requires exactly one h1 and one main")
    if len(parser.styles) != 1:
        failures.append(f"expected one inline style block, observed {len(parser.styles)}")
    if parser.inline_style_count:
        failures.append("inline style attributes are forbidden")
    if parser.forbidden_elements:
        failures.append(
            f"script, link, and base elements are forbidden: {parser.forbidden_elements}"
        )

    bad_classes = sorted(
        token for token in parser.class_tokens if not token.startswith(CLASS_PREFIX)
    )
    if bad_classes:
        failures.append(f"unscoped class tokens: {bad_classes}")
    duplicate_ids = sorted({value for value in parser.ids if parser.ids.count(value) > 1})
    bad_ids = sorted(value for value in parser.ids if not value.startswith(CLASS_PREFIX))
    if duplicate_ids:
        failures.append(f"duplicate DOM ids: {duplicate_ids}")
    if bad_ids:
        failures.append(f"unscoped DOM ids: {bad_ids}")

    if any(not value.split() for value in parser.aria_labelledby):
        failures.append("aria-labelledby must contain at least one DOM id")
    missing_label_ids = sorted(
        {
            target
            for value in parser.aria_labelledby
            for target in value.split()
            if target not in parser.ids
        }
    )
    if missing_label_ids:
        failures.append(
            f"aria-labelledby targets are missing: {missing_label_ids}"
        )

    bad_hrefs = sorted(value for value in parser.hrefs if not _safe_href(value))
    if bad_hrefs:
        failures.append(f"unsafe navigation targets: {bad_hrefs}")
    fragments = {value[1:] for value in parser.hrefs if value.startswith("#")}
    missing_fragments = sorted(fragments - set(parser.ids))
    if missing_fragments:
        failures.append(f"fragment targets are missing: {missing_fragments}")

    if len(parser.images) != 1:
        failures.append(f"expected one reviewed image, observed {len(parser.images)}")
    elif parser.images[0] != {
        "class": "szl-hf-hero-art",
        "src": CANONICAL_ASSET_URL,
        "alt": "",
        "width": "1800",
        "height": "776",
        "fetchpriority": "high",
        "decoding": "async",
    }:
        failures.append("hero image contract drifted from the canonical asset")

    css = "\n".join(parser.styles)
    if CSS_EXTERNAL.search(css):
        failures.append("CSS imports and URL dependencies are forbidden")
    failures.extend(selector_failures(css))
    bad_css_classes = sorted(
        {
            match.group(1)
            for match in CSS_CLASS.finditer(css)
            if not match.group(1).startswith(CLASS_PREFIX)
        }
    )
    bad_css_ids = sorted(
        {
            match.group(1)
            for match in CSS_ID.finditer(css)
            if not match.group(1).startswith(CLASS_PREFIX)
            and not CSS_COLOR.fullmatch(match.group(1))
        }
    )
    if bad_css_classes:
        failures.append(f"unscoped CSS classes: {bad_css_classes}")
    if bad_css_ids:
        failures.append(f"unscoped CSS ids: {bad_css_ids}")

    def mask_css_non_code(source: str) -> str:
        searchable = list(source)
        index = 0
        quote = ""
        in_comment = False
        while index < len(source):
            if in_comment:
                searchable[index] = " "
                if source.startswith("*/", index):
                    searchable[index + 1] = " "
                    in_comment = False
                    index += 2
                    continue
                index += 1
                continue
            if quote:
                searchable[index] = " "
                if source[index] == "\\":
                    if index + 1 < len(source):
                        searchable[index + 1] = " "
                    index += 2
                    continue
                if source[index] == quote:
                    quote = ""
                index += 1
                continue
            if source.startswith("/*", index):
                searchable[index] = searchable[index + 1] = " "
                in_comment = True
                index += 2
                continue
            if source[index] in {'"', "'"}:
                quote = source[index]
                searchable[index] = " "
            index += 1
        return "".join(searchable)

    searchable_css = mask_css_non_code(css)

    def direct_blocks(source: str) -> list[tuple[str, str]]:
        blocks: list[tuple[str, str]] = []
        cursor = 0
        while cursor < len(source):
            open_brace = source.find("{", cursor)
            if open_brace < 0:
                break
            prelude = source[cursor:open_brace]
            if ";" in prelude:
                prelude = prelude.rsplit(";", 1)[-1]
            prelude = re.sub(r"\s+", " ", prelude.strip())
            depth = 1
            index = open_brace + 1
            while index < len(source):
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                index += 1
            if depth:
                break
            if prelude:
                blocks.append((prelude, source[open_brace + 1 : index]))
            cursor = index + 1
        return blocks

    top_level_blocks = direct_blocks(searchable_css)

    def direct_declarations(body: str) -> str:
        declarations = list(body)
        depth = 0
        for index, character in enumerate(body):
            if character == "{":
                depth += 1
                declarations[index] = " "
            elif character == "}":
                declarations[index] = " "
                depth = max(0, depth - 1)
            elif depth:
                declarations[index] = " "
        return "".join(declarations)

    unconditional_rules = [
        (prelude, body, None)
        for prelude, body in top_level_blocks
        if not prelude.startswith("@")
    ]

    def exact_media_rules(
        max_width: int,
    ) -> list[tuple[str, str, int | None]]:
        media_prelude = re.compile(
            rf"@media\s*\(\s*max-width\s*:\s*{max_width}px\s*\)",
            re.IGNORECASE,
        )
        rules: list[tuple[str, str]] = []
        for prelude, body in top_level_blocks:
            if not media_prelude.fullmatch(prelude):
                continue
            rules.extend(
                (child_prelude, child_body, None)
                for child_prelude, child_body in direct_blocks(body)
                if not child_prelude.startswith("@")
            )
        return rules

    def split_top_level_or(value: str) -> list[str]:
        alternatives: list[str] = []
        start = 0
        parentheses = 0
        brackets = 0
        quote = ""
        position = 0
        while position < len(value):
            character = value[position]
            if quote:
                if character == "\\":
                    position += 2
                    continue
                if character == quote:
                    quote = ""
            elif character in {'"', "'"}:
                quote = character
            elif character == "(":
                parentheses += 1
            elif character == ")":
                parentheses = max(0, parentheses - 1)
            elif character == "[":
                brackets += 1
            elif character == "]":
                brackets = max(0, brackets - 1)
            elif (
                not parentheses
                and not brackets
                and value[position : position + 2].casefold() == "or"
                and (position == 0 or not re.match(r"[\w-]", value[position - 1]))
                and (
                    position + 2 == len(value)
                    or not re.match(r"[\w-]", value[position + 2])
                )
            ):
                alternatives.append(value[start:position].strip())
                position += 2
                start = position
                continue
            position += 1
        alternatives.append(value[start:].strip())
        return [item for item in alternatives if item]

    def media_may_apply_at_width(prelude: str, width: int) -> bool:
        if not prelude.lower().startswith("@media"):
            return False
        query_list = prelude[len("@media") :].strip()
        for member in split_selector_members(query_list):
            for query in split_top_level_or(member):
                constraints = re.findall(
                    r"\(\s*(min|max)-width\s*:\s*(\d+)px\s*\)",
                    query,
                    re.IGNORECASE,
                )
                applies = True
                for bound, value in constraints:
                    limit = int(value)
                    if bound.lower() == "min" and width < limit:
                        applies = False
                    if bound.lower() == "max" and width > limit:
                        applies = False
                if applies:
                    return True
        return False

    layer_orders: dict[str, int] = {}
    anonymous_layer_orders: list[int] = []
    next_layer_order = 0
    for layer_match in re.finditer(
        r"(?i)@layer(?:\s+([^;{]+))?\s*(?=[;{])", searchable_css
    ):
        names = split_selector_members((layer_match.group(1) or "").strip())
        if any(names):
            for name in names:
                if name and name not in layer_orders:
                    layer_orders[name] = next_layer_order
                    next_layer_order += 1
        else:
            anonymous_layer_orders.append(next_layer_order)
            next_layer_order += 1

    next_dynamic_layer_order = [next_layer_order]

    def layer_order_for(name: str) -> int:
        if name not in layer_orders:
            layer_orders[name] = next_dynamic_layer_order[0]
            next_dynamic_layer_order[0] += 1
        return layer_orders[name]

    def discover_support_paths(
        blocks: list[tuple[str, str]], path: tuple[int, ...] = ()
    ) -> list[tuple[int, ...]]:
        discovered: list[tuple[int, ...]] = []
        for block_index, (prelude, body) in enumerate(blocks):
            lowered = prelude.lower()
            block_path = path + (block_index,)
            if lowered.startswith("@supports"):
                discovered.append(block_path)
                discovered.extend(
                    discover_support_paths(direct_blocks(body), block_path)
                )
            elif lowered.startswith("@media") or lowered.startswith("@layer"):
                discovered.extend(
                    discover_support_paths(direct_blocks(body), block_path)
                )
        return discovered

    support_paths = discover_support_paths(top_level_blocks)
    protected_property = re.compile(
        r"(?i)(?:^|[;{])\s*(?:--tap|display|min-height|width|max-width|"
        r"grid-template-columns|grid-template|grid|all)\s*:"
    )

    def media_has_unmodeled_state(prelude: str) -> bool:
        conditions = re.findall(r"\(([^()]*)\)", prelude)
        if any(
            re.fullmatch(
                r"\s*(?:min|max)-width\s*:\s*\d+px\s*",
                condition,
                re.IGNORECASE,
            )
            is None
            for condition in conditions
        ):
            return True
        residual = re.sub(r"\([^()]*\)", " ", prelude[len("@media") :])
        media_tokens = re.findall(r"[A-Za-z-]+", residual.casefold())
        return any(
            token not in {"and", "or", "not", "only", "screen", "all"}
            for token in media_tokens
        )

    def discover_conditional_media_paths(
        blocks: list[tuple[str, str]], path: tuple[int, ...] = ()
    ) -> list[tuple[int, ...]]:
        discovered: list[tuple[int, ...]] = []
        for block_index, (prelude, body) in enumerate(blocks):
            lowered = prelude.lower()
            block_path = path + (block_index,)
            if lowered.startswith("@media"):
                if media_has_unmodeled_state(prelude) and protected_property.search(body):
                    discovered.append(block_path)
                discovered.extend(
                    discover_conditional_media_paths(direct_blocks(body), block_path)
                )
            elif lowered.startswith("@supports") or lowered.startswith("@layer"):
                discovered.extend(
                    discover_conditional_media_paths(direct_blocks(body), block_path)
                )
        return discovered

    conditional_media_paths = discover_conditional_media_paths(top_level_blocks)
    conditional_paths = [
        *(("supports", path) for path in support_paths),
        *(("media", path) for path in conditional_media_paths),
    ]
    if len(conditional_paths) > 8:
        failures.append("too many conditional branches for exhaustive cascade validation")
    conditional_scenarios = [
        frozenset(
            conditional_path
            for bit, conditional_path in enumerate(conditional_paths)
            if mask & (1 << bit)
        )
        for mask in range(1 << min(len(conditional_paths), 8))
    ]

    def cascade_rules_at_width(
        width: int,
        enabled_conditions: frozenset[tuple[str, tuple[int, ...]]],
    ) -> list[tuple[str, str, int | None]]:
        anonymous_layer_cursor = [0]

        def collect(
            blocks: list[tuple[str, str]],
            current_layer: tuple[str, int] | None = None,
            path: tuple[int, ...] = (),
            active: bool = True,
        ) -> list[tuple[str, str, int | None]]:
            collected: list[tuple[str, str, int | None]] = []
            for block_index, (prelude, body) in enumerate(blocks):
                lowered = prelude.lower()
                block_path = path + (block_index,)
                if not prelude.startswith("@") and active:
                    collected.append(
                        (
                            prelude,
                            body,
                            None if current_layer is None else current_layer[1],
                        )
                    )
                elif lowered.startswith("@media"):
                    conditional_media_enabled = (
                        block_path not in conditional_media_paths
                        or ("media", block_path) in enabled_conditions
                    )
                    collected.extend(
                        collect(
                            direct_blocks(body),
                            current_layer,
                            block_path,
                            active
                            and conditional_media_enabled
                            and media_may_apply_at_width(prelude, width),
                        )
                    )
                elif lowered.startswith("@supports"):
                    collected.extend(
                        collect(
                            direct_blocks(body),
                            current_layer,
                            block_path,
                            active and ("supports", block_path) in enabled_conditions,
                        )
                    )
                elif lowered.startswith("@layer"):
                    local_name = prelude[len("@layer") :].strip()
                    if local_name:
                        layer_name = (
                            local_name
                            if current_layer is None
                            else f"{current_layer[0]}.{local_name}"
                        )
                        layer_order = layer_order_for(layer_name)
                    else:
                        layer_name = "__anonymous_layer_" + "_".join(
                            str(item) for item in path + (block_index,)
                        )
                        if anonymous_layer_cursor[0] < len(anonymous_layer_orders):
                            layer_order = anonymous_layer_orders[
                                anonymous_layer_cursor[0]
                            ]
                        else:
                            layer_order = layer_order_for(layer_name)
                        anonymous_layer_cursor[0] += 1
                    collected.extend(
                        collect(
                            direct_blocks(body),
                            (layer_name, layer_order),
                            block_path,
                            active,
                        )
                    )
            return collected

        return collect(top_level_blocks)

    def direct_declaration_entries(body: str) -> list[tuple[str, str, bool]]:
        entries: list[tuple[str, str, bool]] = []
        for declaration in direct_declarations(body).split(";"):
            if ":" not in declaration:
                continue
            property_name, value = declaration.split(":", 1)
            property_name = property_name.strip().lower()
            value = re.sub(r"\s+", " ", value.strip())
            important = bool(re.search(r"\s*!important\s*$", value, re.I))
            if important:
                value = re.sub(r"\s*!important\s*$", "", value, flags=re.I)
            if property_name:
                entries.append((property_name, value.strip(), important))
        return entries

    def selector_structure(selector: str) -> tuple[list[str], list[str]]:
        compounds: list[str] = []
        combinators: list[str] = []
        current: list[str] = []
        pending_combinator = ""
        parentheses = 0
        brackets = 0
        quote = ""

        def flush() -> None:
            nonlocal current, pending_combinator
            if not current:
                return
            if compounds:
                combinators.append(pending_combinator or " ")
            compounds.append("".join(current).strip())
            current = []
            pending_combinator = ""

        position = 0
        while position < len(selector):
            character = selector[position]
            if quote:
                current.append(character)
                if character == "\\" and position + 1 < len(selector):
                    position += 1
                    current.append(selector[position])
                elif character == quote:
                    quote = ""
            elif character in {'"', "'"}:
                quote = character
                current.append(character)
            elif character == "[":
                brackets += 1
                current.append(character)
            elif character == "]":
                brackets = max(0, brackets - 1)
                current.append(character)
            elif character == "(":
                parentheses += 1
                current.append(character)
            elif character == ")":
                parentheses = max(0, parentheses - 1)
                current.append(character)
            elif not parentheses and not brackets and (
                character.isspace() or character in ">+~"
            ):
                flush()
                if character in ">+~":
                    pending_combinator = character
                elif compounds and not pending_combinator:
                    pending_combinator = " "
            else:
                current.append(character)
            position += 1
        flush()
        return [item for item in compounds if item], combinators

    def functional_pseudo_classes(compound: str) -> list[tuple[str, str]]:
        functions: list[tuple[str, str]] = []
        position = 0
        brackets = 0
        quote = ""
        while position < len(compound):
            character = compound[position]
            if quote:
                if character == "\\":
                    position += 2
                    continue
                if character == quote:
                    quote = ""
                position += 1
                continue
            if character in {'"', "'"}:
                quote = character
                position += 1
                continue
            if character == "[":
                brackets += 1
                position += 1
                continue
            if character == "]":
                brackets = max(0, brackets - 1)
                position += 1
                continue
            if character != ":" or brackets or compound[position : position + 2] == "::":
                position += 1
                continue
            name_start = position + 1
            name_end = name_start
            while name_end < len(compound) and re.match(r"[\w-]", compound[name_end]):
                name_end += 1
            if name_end >= len(compound) or compound[name_end] != "(":
                position = name_end
                continue
            depth = 1
            argument_start = name_end + 1
            cursor = argument_start
            nested_quote = ""
            while cursor < len(compound) and depth:
                nested = compound[cursor]
                if nested_quote:
                    if nested == "\\":
                        cursor += 2
                        continue
                    if nested == nested_quote:
                        nested_quote = ""
                elif nested in {'"', "'"}:
                    nested_quote = nested
                elif nested == "(":
                    depth += 1
                elif nested == ")":
                    depth -= 1
                cursor += 1
            if depth == 0:
                functions.append(
                    (
                        compound[name_start:name_end].casefold(),
                        compound[argument_start : cursor - 1],
                    )
                )
            position = cursor
        return functions

    def simple_pseudo_classes(compound: str) -> list[str]:
        simple: list[str] = []
        position = 0
        brackets = 0
        quote = ""
        while position < len(compound):
            character = compound[position]
            if quote:
                if character == "\\":
                    position += 2
                    continue
                if character == quote:
                    quote = ""
                position += 1
                continue
            if character in {'"', "'"}:
                quote = character
                position += 1
                continue
            if character == "[":
                brackets += 1
                position += 1
                continue
            if character == "]":
                brackets = max(0, brackets - 1)
                position += 1
                continue
            if character != ":" or brackets or compound[position : position + 2] == "::":
                position += 1
                continue
            name_start = position + 1
            name_end = name_start
            while name_end < len(compound) and re.match(r"[\w-]", compound[name_end]):
                name_end += 1
            if name_end >= len(compound) or compound[name_end] != "(":
                if name_end > name_start:
                    simple.append(compound[name_start:name_end].casefold())
                position = name_end
                continue
            depth = 1
            argument_start = name_end + 1
            position = argument_start
            while position < len(compound) and depth:
                if compound[position] == "(":
                    depth += 1
                elif compound[position] == ")":
                    depth -= 1
                position += 1
            if depth == 0:
                simple.extend(
                    simple_pseudo_classes(compound[argument_start : position - 1])
                )
        return simple

    def without_pseudo_classes(compound: str) -> str:
        result: list[str] = []
        position = 0
        brackets = 0
        quote = ""
        while position < len(compound):
            character = compound[position]
            if quote:
                result.append(character)
                if character == "\\" and position + 1 < len(compound):
                    position += 1
                    result.append(compound[position])
                elif character == quote:
                    quote = ""
                position += 1
                continue
            if character in {'"', "'"}:
                quote = character
                result.append(character)
                position += 1
                continue
            if character == "[":
                brackets += 1
                result.append(character)
                position += 1
                continue
            if character == "]":
                brackets = max(0, brackets - 1)
                result.append(character)
                position += 1
                continue
            if character != ":" or brackets:
                result.append(character)
                position += 1
                continue

            position += 1
            while position < len(compound) and re.match(r"[\w-]", compound[position]):
                position += 1
            if position < len(compound) and compound[position] == "(":
                depth = 1
                position += 1
                nested_quote = ""
                while position < len(compound) and depth:
                    nested = compound[position]
                    if nested_quote:
                        if nested == "\\":
                            position += 2
                            continue
                        if nested == nested_quote:
                            nested_quote = ""
                    elif nested in {'"', "'"}:
                        nested_quote = nested
                    elif nested == "(":
                        depth += 1
                    elif nested == ")":
                        depth -= 1
                    position += 1
        return "".join(result)

    def compound_may_match(
        compound: str,
        element: tuple[str, dict[str, str], int | None],
        element_index: int | None = None,
    ) -> bool:
        if re.search(r"::[A-Za-z_-]", compound):
            return False
        for name, arguments in functional_pseudo_classes(compound):
            if name not in {"not", "is", "where"}:
                continue
            argument_matches = []
            for member in split_selector_members(arguments):
                argument_matches.append(
                    selector_may_match_target(member, element_index)
                    if element_index is not None
                    else False
                )
            if name == "not" and any(argument_matches):
                return False
            if name in {"is", "where"} and not any(argument_matches):
                return False
        tag, attributes, _ = element
        form_controls = {
            "button",
            "fieldset",
            "input",
            "optgroup",
            "option",
            "select",
            "textarea",
        }
        for name in simple_pseudo_classes(compound):
            if name == "disabled" and not (
                tag in form_controls and "disabled" in attributes
            ):
                return False
            if name == "enabled" and not (
                tag in form_controls and "disabled" not in attributes
            ):
                return False
            if name in {"link", "any-link"} and not (
                tag in {"a", "area"} and bool(attributes.get("href"))
            ):
                return False
            if name == "root":
                return False
        base = without_pseudo_classes(compound)
        without_attributes = re.sub(r"\[[^]]*\]", "", base)
        required_ids = CSS_ID.findall(without_attributes)
        if required_ids and any(value != attributes.get("id", "") for value in required_ids):
            return False
        classes = set(attributes.get("class", "").split())
        if any(value not in classes for value in CSS_CLASS.findall(without_attributes)):
            return False

        simple = CSS_ID.sub("", CSS_CLASS.sub("", without_attributes))
        simple = simple.replace("*", "").strip()
        tag_match = re.match(r"^[A-Za-z][A-Za-z0-9_-]*", simple)
        if tag_match and tag_match.group(0).lower() != tag.lower():
            return False

        attribute_pattern = re.compile(
            r"^\s*([A-Za-z_:][\w:.-]*)"
            r"(?:\s*([~|^$*]?=)\s*"
            r"(?:\"([^\"]*)\"|'([^']*)'|([^\]\s]+))"
            r"\s*([isIS])?)?\s*$"
        )
        for raw_attribute in re.findall(r"\[([^]]*)\]", base):
            parsed = attribute_pattern.fullmatch(raw_attribute)
            if parsed is None:
                continue
            name, operator, double, single, bare, flag = parsed.groups()
            actual = attributes.get(name.lower())
            if actual is None:
                return False
            if operator is None:
                continue
            expected = next(
                value for value in (double, single, bare) if value is not None
            )
            if flag and flag.lower() == "i":
                actual = actual.casefold()
                expected = expected.casefold()
            if operator == "=" and actual != expected:
                return False
            if operator == "~=" and expected not in actual.split():
                return False
            if operator == "|=" and actual != expected and not actual.startswith(expected + "-"):
                return False
            if operator == "^=" and not actual.startswith(expected):
                return False
            if operator == "$=" and not actual.endswith(expected):
                return False
            if operator == "*=" and expected not in actual:
                return False
        return True

    def selector_targets(selector: str) -> list[int]:
        return [
            element_index
            for element_index in range(len(parser.elements))
            if selector_may_match_target(selector, element_index)
        ]

    def selector_may_match_target(
        candidate: str, target_index: int | None
    ) -> bool:
        if target_index is None:
            return False
        compounds, combinators = selector_structure(candidate)
        if not compounds or len(combinators) != len(compounds) - 1:
            return False

        def previous_siblings(element_index: int) -> list[int]:
            parent_index = parser.elements[element_index][2]
            return [
                sibling_index
                for sibling_index, sibling in enumerate(parser.elements[:element_index])
                if sibling[2] == parent_index
            ]

        def matches(compound_index: int, element_index: int) -> bool:
            if not compound_may_match(
                compounds[compound_index],
                parser.elements[element_index],
                element_index,
            ):
                return False
            if compound_index == 0:
                return True
            combinator = combinators[compound_index - 1]
            if combinator == ">":
                parent_index = parser.elements[element_index][2]
                return parent_index is not None and matches(
                    compound_index - 1, parent_index
                )
            if combinator == "+":
                siblings = previous_siblings(element_index)
                return bool(siblings) and matches(compound_index - 1, siblings[-1])
            if combinator == "~":
                return any(
                    matches(compound_index - 1, sibling_index)
                    for sibling_index in reversed(previous_siblings(element_index))
                )
            ancestor_index = parser.elements[element_index][2]
            while ancestor_index is not None:
                if matches(compound_index - 1, ancestor_index):
                    return True
                ancestor_index = parser.elements[ancestor_index][2]
            return False

        return matches(len(compounds) - 1, target_index)

    def winning_declaration(
        rules: list[tuple[str, str, int | None]],
        selector: str,
        property_name: str,
    ) -> list[tuple[str, bool] | None]:
        expected_selector = re.sub(r"\s+", " ", selector.strip())
        target_indices = selector_targets(expected_selector)

        def specificity(candidate: str) -> tuple[int, int, int]:
            without_functions = candidate
            functional_specificity = (0, 0, 0)
            for name, arguments in functional_pseudo_classes(candidate):
                marker = re.compile(
                    rf":{re.escape(name)}\s*\({re.escape(arguments)}\)",
                    re.IGNORECASE,
                )
                without_functions = marker.sub("", without_functions, count=1)
                if name == "where":
                    continue
                if name in {"is", "not", "has"}:
                    argument_specificities = [
                        specificity(member)
                        for member in split_selector_members(arguments)
                    ]
                    if argument_specificities:
                        selected = max(argument_specificities)
                        functional_specificity = tuple(
                            left + right
                            for left, right in zip(
                                functional_specificity, selected, strict=True
                            )
                        )
                else:
                    functional_specificity = (
                        functional_specificity[0],
                        functional_specificity[1] + 1,
                        functional_specificity[2],
                    )
            ids = len(re.findall(r"#[\w-]+", without_functions))
            classes = len(
                re.findall(
                    r"\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+", without_functions
                )
            )
            without_simple = re.sub(
                r"#[\w-]+|\.[\w-]+|\[[^\]]+\]|::?[\w-]+(?:\([^)]*\))?",
                " ",
                without_functions,
            )
            elements = len(re.findall(r"\b[a-zA-Z][\w-]*\b", without_simple))
            return tuple(
                left + right
                for left, right in zip(
                    (ids, classes, elements), functional_specificity, strict=True
                )
            )

        resetters = {
            "grid-template-columns": {"grid", "grid-template", "all"},
        }
        if not property_name.startswith("--"):
            resetters.setdefault(property_name, set()).add("all")

        winners: dict[
            int, tuple[str, bool, tuple[int, int, int], int | None] | None
        ] = {
            target_index: None for target_index in target_indices
        }
        uncertain_pseudo_targets: set[int] = set()
        deterministic_simple_pseudos = {
            "any-link",
            "disabled",
            "enabled",
            "link",
            "root",
        }
        for prelude, body, layer_order in rules:
            matching_specificities: dict[int, tuple[int, int, int]] = {}
            unsupported_targets: set[int] = set()
            unconditional_targets: set[int] = set()
            for item in split_selector_members(prelude):
                candidate = re.sub(r"\s+", " ", item.strip())
                candidate_specificity = specificity(candidate)
                unsupported_pseudos = set(simple_pseudo_classes(candidate)) - (
                    deterministic_simple_pseudos
                )
                unsupported_pseudos.update(
                    name
                    for name, _ in functional_pseudo_classes(candidate)
                    if name not in {"is", "not", "where"}
                )
                compounds, combinators = selector_structure(candidate)
                stripped_compounds = [
                    without_pseudo_classes(compound).strip() or "*"
                    for compound in compounds
                ]
                stripped_candidate = stripped_compounds[0] if stripped_compounds else ""
                for combinator, compound in zip(
                    combinators, stripped_compounds[1:], strict=True
                ):
                    stripped_candidate += f" {combinator} {compound}"
                for target_index in target_indices:
                    if not selector_may_match_target(candidate, target_index):
                        if unsupported_pseudos and selector_may_match_target(
                            stripped_candidate, target_index
                        ):
                            unsupported_targets.add(target_index)
                        continue
                    if unsupported_pseudos:
                        unsupported_targets.add(target_index)
                    else:
                        unconditional_targets.add(target_index)
                    previous = matching_specificities.get(target_index)
                    if previous is None or candidate_specificity > previous:
                        matching_specificities[target_index] = candidate_specificity
            relevant_targets = unsupported_targets - unconditional_targets
            for candidate_property, value, important in direct_declaration_entries(body):
                if candidate_property == property_name:
                    candidate_value = value
                elif candidate_property in resetters.get(property_name, set()):
                    candidate_value = f"__reset_by_{candidate_property}__"
                else:
                    continue
                uncertain_pseudo_targets.update(relevant_targets)
                for target_index, candidate_specificity in matching_specificities.items():
                    winner = winners[target_index]
                    if important:
                        layer_priority = (
                            1,
                            -layer_order if layer_order is not None else 0,
                        ) if layer_order is not None else (0, 0)
                    else:
                        layer_priority = (
                            (0, layer_order)
                            if layer_order is not None
                            else (1, 0)
                        )
                    candidate_priority = (
                        int(important),
                        *layer_priority,
                        *candidate_specificity,
                    )
                    if winner is not None:
                        winner_layer = winner[3]
                        if winner[1]:
                            winner_layer_priority = (
                                (1, -winner_layer)
                                if winner_layer is not None
                                else (0, 0)
                            )
                        else:
                            winner_layer_priority = (
                                (0, winner_layer)
                                if winner_layer is not None
                                else (1, 0)
                            )
                        winner_priority = (
                            int(winner[1]),
                            *winner_layer_priority,
                            *winner[2],
                        )
                        if winner_priority > candidate_priority:
                            continue
                    winners[target_index] = (
                        candidate_value,
                        important,
                        candidate_specificity,
                        layer_order,
                    )
        results = [
            None if winners[target_index] is None else winners[target_index][:2]
            for target_index in target_indices
        ]
        results.extend(
            ("__unmodeled_pseudo_state__", True)
            for _ in sorted(uncertain_pseudo_targets)
        )
        return results

    def responsive_sample_widths(max_width: int) -> list[int]:
        minimum_width = 320
        samples = {minimum_width, max_width}

        def collect_boundaries(blocks: list[tuple[str, str]]) -> None:
            for prelude, body in blocks:
                lowered = prelude.lower()
                if lowered.startswith("@media"):
                    for bound, value in re.findall(
                        r"\(\s*(min|max)-width\s*:\s*(\d+)px\s*\)",
                        prelude,
                        re.IGNORECASE,
                    ):
                        boundary = int(value)
                        if not minimum_width <= boundary <= max_width:
                            continue
                        samples.add(boundary)
                        adjacent = (
                            boundary - 1 if bound.lower() == "min" else boundary + 1
                        )
                        if minimum_width <= adjacent <= max_width:
                            samples.add(adjacent)
                    collect_boundaries(direct_blocks(body))
                elif lowered.startswith("@supports"):
                    collect_boundaries(direct_blocks(body))
                elif lowered.startswith("@layer"):
                    collect_boundaries(direct_blocks(body))

        collect_boundaries(top_level_blocks)
        return sorted(samples)

    def winner_matches(
        winners: list[tuple[str, bool] | None],
        value_pattern: str,
        required_important: bool | None = None,
    ) -> bool:
        return bool(winners) and all(
            winner is not None
            and re.fullmatch(value_pattern, winner[0], re.I)
            and (required_important is None or winner[1] is required_important)
            for winner in winners
        )

    global_requirements = (
        ("44px touch token", ROOT_SELECTOR, "--tap", r"44px", None),
        (
            "48px CTA",
            f"{ROOT_SELECTOR} .szl-hf-button",
            "display",
            r"inline-flex",
            True,
        ),
        (
            "48px CTA",
            f"{ROOT_SELECTOR} .szl-hf-button",
            "min-height",
            r"48px",
            None,
        ),
        (
            "44px navigation",
            f"{ROOT_SELECTOR} nav a",
            "min-height",
            r"var\(\s*--tap\s*\)",
            None,
        ),
        (
            "bounded embedded shell",
            f"{ROOT_SELECTOR} .szl-hf-shell",
            "width",
            r"min\(\s*1180px\s*,\s*calc\(\s*100%\s*-\s*40px\s*\)\s*\)",
            None,
        ),
        (
            "bounded embedded shell",
            f"{ROOT_SELECTOR} .szl-hf-shell",
            "max-width",
            r"100%",
            None,
        ),
    )
    media_boundaries = [
        int(value)
        for _, value in re.findall(
            r"\(\s*(min|max)-width\s*:\s*(\d+)px\s*\)",
            searchable_css,
            re.IGNORECASE,
        )
    ]
    global_sample_widths = responsive_sample_widths(
        max([4096, *media_boundaries])
    )
    failed_global_contracts: list[str] = []
    for label, selector, property_name, value_pattern, important in global_requirements:
        cascade_value_pattern = value_pattern
        if label == "bounded embedded shell" and property_name == "width":
            cascade_value_pattern = (
                rf"(?:{value_pattern}|"
                r"calc\(\s*100%\s*-\s*(?:18|24)px\s*\))"
            )
        unconditional_winner = winning_declaration(
            unconditional_rules, selector, property_name
        )
        cascade_winners = [
            winning_declaration(
                cascade_rules_at_width(width, support_scenario),
                selector,
                property_name,
            )
            for width in global_sample_widths
            for support_scenario in conditional_scenarios
        ]
        if (
            not winner_matches(unconditional_winner, value_pattern, important)
            or not all(
                winner_matches(winner, cascade_value_pattern, important)
                for winner in cascade_winners
            )
        ) and label not in failed_global_contracts:
            failed_global_contracts.append(label)
    for label in failed_global_contracts:
            failures.append(f"missing {label} contract")
    responsive_requirements = (
        (
            "one-column mobile CTA",
            640,
            f"{ROOT_SELECTOR} .szl-hf-actions .szl-hf-button",
            "width",
            r"100%",
            True,
        ),
        (
            "mobile navigation reflow",
            760,
            f"{ROOT_SELECTOR} nav",
            "grid-template-columns",
            r"repeat\(\s*2\s*,\s*minmax\(\s*0\s*,\s*1fr\s*\)\s*\)",
            None,
        ),
        (
            "compact mobile hero",
            640,
            f"{ROOT_SELECTOR} .szl-hf-hero",
            "min-height",
            r"0",
            None,
        ),
        (
            "single-column mobile evidence loop",
            640,
            f"{ROOT_SELECTOR} .szl-hf-steps",
            "grid-template-columns",
            r"1fr",
            None,
        ),
    )
    for label, max_width, selector, property_name, value_pattern, important in responsive_requirements:
        exact_winner = winning_declaration(
            exact_media_rules(max_width), selector, property_name
        )
        cascade_winners = [
            winning_declaration(
                cascade_rules_at_width(width, support_scenario),
                selector,
                property_name,
            )
            for width in responsive_sample_widths(max_width)
            for support_scenario in conditional_scenarios
        ]
        if not winner_matches(
            exact_winner, value_pattern, important
        ) or not all(
            winner_matches(winner, value_pattern, important)
            for winner in cascade_winners
        ):
            failures.append(f"missing {label} contract")
    conditional_markers = {
        "prefers-reduced-motion": re.compile(
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)",
            re.IGNORECASE,
        ),
        "prefers-contrast": re.compile(
            r"@media\s*\(\s*prefers-contrast\s*:\s*more\s*\)",
            re.IGNORECASE,
        ),
        "forced-colors": re.compile(
            r"@media\s*\(\s*forced-colors\s*:\s*active\s*\)",
            re.IGNORECASE,
        ),
    }
    top_level_preludes = [prelude for prelude, _ in top_level_blocks]
    for marker, pattern in conditional_markers.items():
        if not any(pattern.fullmatch(prelude) for prelude in top_level_preludes):
            failures.append(f"missing CSS marker: {marker}")
    unconditional_declarations = re.sub(
        r"\s+",
        " ",
        " ".join(
            direct_declarations(body)
            for prelude, body in top_level_blocks
            if not prelude.startswith("@")
        ),
    )
    for marker in (
        "safe-area-inset-top",
        "safe-area-inset-right",
        "safe-area-inset-bottom",
        "safe-area-inset-left",
        "overflow-wrap: anywhere",
    ):
        if marker not in unconditional_declarations:
            failures.append(f"missing CSS marker: {marker}")
    if re.search(
        r"(?i)overflow-x\s*:\s*(?:hidden|auto|clip)", searchable_css
    ):
        failures.append("horizontal overflow must remain observable")

    if 'href="#szl-hf-main"' not in document:
        failures.append("keyboard skip link is missing")
    if CANONICAL_DEPLOYMENT_URL not in document:
        failures.append("absolute deployment source binding is missing")
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    source = root / "huggingface/org-card/index.html"
    failures = validate_document(source.read_text(encoding="utf-8"))
    report = {
        "schema": "szl.hf-org-card-embed-check/v2",
        "state": "PASS" if not failures else "FAIL",
        "source": source.relative_to(root).as_posix(),
        "failures": failures,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
