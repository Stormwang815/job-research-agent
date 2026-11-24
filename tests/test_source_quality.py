from app.source_quality import curate_sources, normalize_url, score_source


def test_normalize_url_removes_tracking_and_fragment():
    assert normalize_url("HTTPS://Example.com/jobs/?utm_source=x&id=1#detail") == "https://example.com/jobs?id=1"


def test_curate_sources_deduplicates_and_scores():
    sources = curate_sources([
        {"url": "https://example.gov.cn/jobs?utm_source=a", "title": "A"},
        {"url": "https://example.gov.cn/jobs", "title": "duplicate"},
        {"url": "https://www.zhaopin.com/job/1", "title": "B"},
    ])
    assert len(sources) == 2
    assert sources[0]["trust_score"] == 95
    assert sources[0]["trust_tier"] == "权威机构"


def test_unknown_source_has_conservative_score():
    assert score_source("https://some-blog.example/post") == ("普通网页", 55)

