from recipes_mcp.config import Blog
from recipes_mcp.search import (
    SearchResult,
    merge_results,
    normalize_url,
    parse_blogger,
    parse_searxng,
    parse_wordpress,
)

BLOGS = [Blog(name="A", domain="a.com"), Blog(name="B", domain="b.com")]


def test_parse_wordpress():
    items = [{"title": {"rendered": "Tom &amp; Jerry <b>Pie</b>"}, "link": "https://a.com/p", "excerpt": {"rendered": "<p>Yum</p>"}}]
    [r] = parse_wordpress(items, "A")
    assert (r.title, r.url, r.snippet) == ("Tom & Jerry Pie", "https://a.com/p", "Yum")


def test_parse_blogger():
    feed = {"feed": {"entry": [{"title": {"$t": "Pie"}, "link": [{"rel": "self", "href": "x"}, {"rel": "alternate", "href": "https://a.com/pie"}], "summary": {"$t": "tasty"}}]}}
    [r] = parse_blogger(feed, "A")
    assert r.url == "https://a.com/pie" and r.snippet == "tasty"


def test_parse_searxng_filters_to_allowlist():
    data = {"results": [{"title": "t", "url": "https://www.a.com/x", "content": "c"}, {"title": "t", "url": "https://other.com/x"}]}
    results = parse_searxng(data, BLOGS)
    assert [r.site for r in results] == ["A"]


def test_normalize_url():
    assert normalize_url("https://www.A.com/x/?q=1#f") == "a.com/x"


def test_merge_round_robin_and_dedupe():
    def r(site, n):
        return SearchResult("t", f"https://{site}.com/{n}", site, "")

    merged = merge_results([[r("a", 1), r("a", 2), r("a", 3)], [r("b", 1), r("a", 1)]], limit=4)
    assert [x.url for x in merged] == ["https://a.com/1", "https://b.com/1", "https://a.com/2", "https://a.com/3"]
