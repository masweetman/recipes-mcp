import json

import pytest

from recipes_mcp.extract import extract_recipe

RECIPE = {
    "@context": "https://schema.org",
    "@type": "Recipe",
    "name": "Test Pie",
    "recipeIngredient": ["1 cup flour", "2 eggs"],
    "recipeInstructions": [{"@type": "HowToStep", "text": "Mix."}, {"@type": "HowToStep", "text": "Bake."}],
    "recipeYield": "4 servings",
    "totalTime": "PT45M",
}


def page(body: str) -> str:
    return f"<html><head>{body}</head><body></body></html>"


def test_extracts_json_ld_from_unsupported_site():
    html = page(f'<script type="application/ld+json">{json.dumps(RECIPE)}</script>')
    r = extract_recipe(html, "https://unknown-blog.example/pie")
    assert r["title"] == "Test Pie"
    assert r["ingredients"] == ["1 cup flour", "2 eggs"]
    assert r["instructions_list"] == ["Mix.", "Bake."]
    assert r["total_time"] == 45


def test_no_recipe_raises():
    with pytest.raises(ValueError):
        extract_recipe(page(""), "https://unknown-blog.example/x")


def test_prose_fallback_returns_post_body_text():
    html = (
        "<html><head><title>Loaf</title><script>var x=1;</script></head><body>"
        "<div class='nav'>Menu</div><div class='post-body entry'>Ingredients:<br>2 eggs<p>Bake it.</p></div>"
        "</body></html>"
    )
    r = extract_recipe(html, "https://unknown-blog.example/x")
    assert r["structured"] is False
    assert r["title"] == "Loaf"
    assert r["page_text"].splitlines() == ["Ingredients:", "2 eggs", "Bake it."]
