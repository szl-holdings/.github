from pathlib import Path


def test_org_card_navigation_has_full_size_hit_regions() -> None:
    html = Path("huggingface/org-card/index.html").read_text(encoding="utf-8")
    rule = html.split("#szl-hf-org-card nav a {", 1)[1].split("}", 1)[0]
    assert "min-width: 48px" in rule
    assert "height: 48px" in rule
    assert "min-height: var(--tap)" in rule
    assert "justify-content: center" in rule
    assert "border-radius: 10px" in rule
    assert "border-radius: 999px" not in rule
