from backend.social import generator as g


def test_hashtags_clean_and_unique():
    assert g.clean_hashtags("#GTA, gta  police!! chase") == "#GTA #police #chase"
    assert g.clean_hashtags(["a b", "#c"]) == "#ab #c"


def test_parse_json_with_fence_and_junk():
    d = g.parse_json('Here:\n```json\n{"title": "Hi"}\n```')
    assert d == {"title": "Hi"}
    assert g.parse_json("no json here") is None


def test_local_fallback_has_all_fields():
    f = g.local_fallback("Epic police chase", "Police Chase", "viral")
    assert set(f) == set(g.FIELDS)
    assert f["title"] and f["hashtags"].startswith("#") and f["cta"]


def test_no_key_uses_local(monkeypatch):
    monkeypatch.setattr(g, "is_configured", lambda: False)
    f, src, warn = g.generate("T", "L", "", "", "", "funny", "general")
    assert src == "local" and warn and f["title"]


def test_bad_reply_falls_back(monkeypatch):
    monkeypatch.setattr(g, "is_configured", lambda: True)
    monkeypatch.setattr(g, "ask", lambda p: "nonsense")
    f, src, warn = g.generate("T", "L", "", "", "", "viral", "general")
    assert src == "local" and "could not be read" in warn


def test_gemini_error_falls_back(monkeypatch):
    monkeypatch.setattr(g, "is_configured", lambda: True)

    def boom(p):
        raise RuntimeError("quota")
    monkeypatch.setattr(g, "ask", boom)
    f, src, warn = g.generate("T", "L", "", "", "", "viral", "general")
    assert src == "local" and "quota" in warn


def test_good_reply_used_and_prompt_has_only_given_facts(monkeypatch):
    seen = {}
    monkeypatch.setattr(g, "is_configured", lambda: True)

    def fake(p):
        seen["p"] = p
        return '{"title":"Big Moment","description":"d","caption":"c","hashtags":["gta","chase"],"keywords":["a","b"],"cta":"x","pinned_comment":"y"}'
    monkeypatch.setattr(g, "ask", fake)
    f, src, warn = g.generate("My clip", "Explosions", "", "", "", "cinematic", "tiktok")
    assert src == "gemini" and warn is None and f["title"] == "Big Moment" and f["hashtags"] == "#gta #chase"
    assert "My clip" in seen["p"] and "Explosions" in seen["p"] and "Do not invent" in seen["p"]