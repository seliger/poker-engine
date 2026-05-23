"""Unit tests for DeckConfig (Deck Layer)."""

import pytest

from backend.deck.card import DeckConfig


class TestDeckConfigPresets:
    def test_standard_preset_defaults(self) -> None:
        cfg = DeckConfig.STANDARD()
        assert cfg.include_orbs is False
        assert cfg.include_nulls is False
        assert cfg.null_exists_in_orbs is False
        assert cfg.nulls_match_each_other is False
        assert cfg.wilds_can_become_null is False

    def test_with_nulls_preset(self) -> None:
        cfg = DeckConfig.WITH_NULLS()
        assert cfg.include_nulls is True
        assert cfg.include_orbs is False

    def test_with_orbs_preset(self) -> None:
        cfg = DeckConfig.WITH_ORBS()
        assert cfg.include_orbs is True
        assert cfg.include_nulls is False

    def test_preset_fields_overridable(self) -> None:
        cfg = DeckConfig.WITH_NULLS()
        cfg.nulls_match_each_other = True
        assert cfg.nulls_match_each_other is True


class TestDeckConfigSerialization:
    def test_standard_roundtrip_json(self) -> None:
        original = DeckConfig.STANDARD()
        restored = DeckConfig.from_json(original.to_json())
        assert restored.include_orbs == original.include_orbs
        assert restored.include_nulls == original.include_nulls
        assert restored.null_exists_in_orbs == original.null_exists_in_orbs
        assert restored.nulls_match_each_other == original.nulls_match_each_other
        assert restored.wilds_can_become_null == original.wilds_can_become_null
        assert restored.low_card_warning_threshold == original.low_card_warning_threshold

    def test_with_nulls_roundtrip_json(self) -> None:
        original = DeckConfig.WITH_NULLS()
        restored = DeckConfig.from_json(original.to_json())
        assert restored.include_nulls is True

    def test_with_orbs_roundtrip_json(self) -> None:
        original = DeckConfig.WITH_ORBS()
        restored = DeckConfig.from_json(original.to_json())
        assert restored.include_orbs is True

    def test_custom_config_roundtrip_json(self) -> None:
        original = DeckConfig(
            include_orbs=True,
            include_nulls=True,
            null_exists_in_orbs=True,
            nulls_match_each_other=True,
            wilds_can_become_null=True,
            low_card_warning_threshold=7,
        )
        restored = DeckConfig.from_json(original.to_json())
        assert restored.include_orbs is True
        assert restored.include_nulls is True
        assert restored.null_exists_in_orbs is True
        assert restored.nulls_match_each_other is True
        assert restored.wilds_can_become_null is True
        assert restored.low_card_warning_threshold == 7

    def test_to_json_is_valid_json_string(self) -> None:
        import json
        cfg = DeckConfig.WITH_ORBS()
        parsed = json.loads(cfg.to_json())
        assert isinstance(parsed, dict)

    def test_roundtrip_no_data_loss_via_dict(self) -> None:
        original = DeckConfig(
            include_orbs=True,
            include_nulls=False,
            null_exists_in_orbs=False,
            nulls_match_each_other=False,
            wilds_can_become_null=True,
        )
        restored = DeckConfig.from_dict(original.to_dict())
        assert restored.include_orbs == original.include_orbs
        assert restored.wilds_can_become_null == original.wilds_can_become_null
