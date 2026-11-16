from discord import RadioGroupOption
from discord.ui import Label, RadioGroup

from core.enums.language import SupportedLanguage
from features.misc.builder.container.translations import t, ts


def spoiler_group(language: SupportedLanguage, *, spoiler: bool = False) -> RadioGroup:
    """The yes/no choice whether a media is hidden behind a spoiler warning; `spoiler` is the choice made so far."""
    return RadioGroup(
        options=[
            RadioGroupOption(label=ts(language, "modals.option_no"), value="no", default=not spoiler),
            RadioGroupOption(label=ts(language, "modals.option_yes"), value="yes", default=spoiler),
        ]
    )


def spoiler_label(language: SupportedLanguage, group: RadioGroup) -> Label:
    """The spoiler choice `group` with its question."""
    return Label(text=t(language, "modals.spoiler.question"), component=group)
