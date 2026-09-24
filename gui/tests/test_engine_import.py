import boss_cdp_raw


def test_engine_importable_and_version_locked():
    assert boss_cdp_raw.__version__ == "2.2.0"


def test_engine_constants_intact():
    assert boss_cdp_raw.DEFAULT_CDP_PORT == 9222
    assert boss_cdp_raw.MAX_API_REQUESTS == 500
