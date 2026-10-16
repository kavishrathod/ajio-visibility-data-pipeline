from src.config import load_config


def test_config_has_50_unique_keywords_and_two_expected_zeroes():
    config = load_config()
    assert len(config.keywords) == 50
    assert len(set(config.keywords)) == 50
    assert set(config.targets["expected_zero_result_keywords"]) == {"zxqvbn shirt", "asdfgh qwerty zzzz"}
    assert all(word in config.keywords for word in config.targets["expected_zero_result_keywords"])
