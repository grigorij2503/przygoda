"""Separate character speech from action mechanics and preserve it in narration."""

import re
import unicodedata
from collections import Counter
from typing import TYPE_CHECKING, Iterable, TypedDict

if TYPE_CHECKING:
    from app.models import Character


_SPOKEN_LINE = re.compile(r'"(?P<plain>[^"]*)"|„(?P<polish>[^”]*)”|“(?P<curly>[^”]*)”')


class DialogueRecipient(TypedDict):
    character_id: int
    character_name: str


class SpokenLine(TypedDict):
    text: str
    narration_text: str
    recipients: list[DialogueRecipient]


def split_action_dialogue(action_text: str) -> tuple[str, tuple[str, ...]]:
    """Recognize complete quote pairs; leave unmatched quotes in the description."""
    spoken_lines: list[str] = []

    def remove_speech(match: re.Match[str]) -> str:
        text = next(value for value in match.groups() if value is not None).strip()
        if text:
            spoken_lines.append(text)
        return " "

    description = _SPOKEN_LINE.sub(remove_speech, action_text).strip()
    return description, tuple(spoken_lines)


def action_mechanics_text(action_text: str) -> str:
    """Only the unquoted description declares mechanical action or equipment use."""
    return split_action_dialogue(action_text)[0]


def build_action_dialogue(
    action_text: str, characters: Iterable["Character"],
) -> list[SpokenLine]:
    """Resolve complete @names within speech against the supplied room roster."""
    spoken_lines = split_action_dialogue(action_text)[1]
    if not spoken_lines:
        return []
    names: dict[str, list["Character"]] = {}
    for character in characters:
        if not character.is_participating or not character.name.strip():
            continue
        key = unicodedata.normalize("NFC", character.name).casefold()
        names.setdefault(key, []).append(character)
    unique_names = {key: matches[0] for key, matches in names.items() if len(matches) == 1}
    mention_pattern = (
        re.compile(
            r"(?<![\w@])@(" + "|".join(
                re.escape(name) for name in sorted(names, key=len, reverse=True)
            ) + r")(?!\w)",
            re.IGNORECASE,
        )
        if names else None
    )
    result: list[SpokenLine] = []
    for text in spoken_lines:
        recipients: list[DialogueRecipient] = []

        def resolve_mention(match: re.Match[str]) -> str:
            character = unique_names.get(match.group(1).casefold())
            if character is None:
                return match.group(0)
            if not any(recipient["character_id"] == character.id for recipient in recipients):
                recipients.append({
                    "character_id": character.id,
                    "character_name": character.name,
                })
            return character.name

        narration_text = (
            mention_pattern.sub(resolve_mention, unicodedata.normalize("NFC", text))
            if mention_pattern else text
        )
        result.append({"text": text, "narration_text": narration_text, "recipients": recipients})
    return result


def narrate_spoken_line(character_name: str, line: SpokenLine) -> str:
    recipients = ", ".join(recipient["character_name"] for recipient in line["recipients"])
    introduction = (
        f"{character_name} zwraca się do postaci {recipients} ze słowami"
        if recipients else f"{character_name} mówi"
    )
    punctuation = "" if line["narration_text"].endswith((".", "!", "?", "…")) else "."
    return f'{introduction}: „{line["narration_text"]}”{punctuation}'


def preserve_action_dialogue(
    narration: str, actions: Iterable[dict], characters: Iterable["Character"],
) -> str:
    """Restore omitted speech after prose cleanup without changing any outcomes."""
    roster = list(characters)
    dialogue = [
        (action["character_name"], line)
        for action in actions
        for line in build_action_dialogue(action.get("action_text") or "", roster)
    ]
    if not dialogue:
        return narration
    replacements = {line["text"]: line["narration_text"] for _, line in dialogue}

    def replace_mention(match: re.Match[str]) -> str:
        text = next(value for value in match.groups() if value is not None)
        replacement = replacements.get(text.strip())
        if replacement is None:
            return match.group(0)
        return match.group(0)[0] + replacement + match.group(0)[-1]

    narration = _SPOKEN_LINE.sub(replace_mention, narration)
    available = Counter(
        unicodedata.normalize("NFC", text) for text in split_action_dialogue(narration)[1]
    )
    missing = []
    for character_name, line in dialogue:
        text = unicodedata.normalize("NFC", line["narration_text"])
        if available[text] > 0:
            available[text] -= 1
        else:
            missing.append(narrate_spoken_line(character_name, line))
    return narration + ("\n\n" + " ".join(missing) if missing else "")
