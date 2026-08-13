from pathlib import Path


def test_dashboard_uses_sow_name_as_primary_litter_attention_identity():
    source = Path("static/js/dashboard.js").read_text(encoding="utf-8")
    assert 'const sowName = item.sow_name || item.sow_tag_number || ""' in source
    assert 'headline: sowName || item.litter_id || "Litter"' in source
    assert 'litterContext' in source


def test_dashboard_attention_is_read_only_presentation():
    source = Path("static/js/dashboard.js").read_text(encoding="utf-8")
    assert 'addAttention("litter"' in source
    assert 'fetch(' not in source[source.index('function litterAttentionIdentity'):source.index('function litterAttentionIdentity') + 350]
