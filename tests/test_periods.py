from app.services.transformer import normalize_period

def test_periods():
    assert normalize_period('c2025 Feb')=='2025-02'
    assert normalize_period('01.2020')=='2020-01'
    assert normalize_period('January/2020')=='2020-01'
    assert normalize_period('2024-7')=='2024-07'
