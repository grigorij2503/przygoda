from types import SimpleNamespace

from app.gemini_service import (
    CLASS_ARCHETYPE_INSTRUCTION,
    narrative_form_instruction,
)


def test_narrative_form_is_independent_from_masculine_class_archetype():
    feminine_character = SimpleNamespace(
        character_class="Łącznik",
        narrative_form="feminine",
    )

    instruction = narrative_form_instruction(feminine_character)

    assert "ona" in instruction
    assert "zrobiła" in instruction
    assert "nie określa płci" in CLASS_ARCHETYPE_INSTRUCTION
    assert "Nie odmieniaj jej na formę żeńską" in CLASS_ARCHETYPE_INSTRUCTION
