from core.discord_api.limits import MAX_V2_MEDIA_GALLERY_ITEMS, MAX_V2_TEXT_DISPLAY_LENGTH
from core.enums.language import SupportedLanguage
from core.i18n.translator import translate
from features.misc.builder.container.models import ComponentKind
from features.misc.builder.formatting import format_number


def t(language: SupportedLanguage, key: str, /, count: int | None = None, **variables: object) -> str:
    """Translate a key of the `container` locale domain."""
    return translate(language, f"builder.container.{key}", count, **variables)


def ts(language: SupportedLanguage, key: str, /, count: int | None = None, **variables: object) -> str:
    """Translate a key both builders share (`locales/<lang>/builder/builder.json`)."""
    return translate(language, f"builder.{key}", count, **variables)


def kind_label(language: SupportedLanguage, kind: ComponentKind) -> str:
    return t(language, f"info.kinds.{kind.value}.label")


def kind_info_text(language: SupportedLanguage, kind: ComponentKind) -> str:
    limits: dict[ComponentKind, str] = {
        ComponentKind.TEXT_DISPLAY: format_number(language, MAX_V2_TEXT_DISPLAY_LENGTH),
        ComponentKind.MEDIA_GALLERY: str(MAX_V2_MEDIA_GALLERY_ITEMS),
    }
    return t(language, f"info.kinds.{kind.value}.description", max=limits.get(kind, ""))


def kind_empty_text(language: SupportedLanguage, kind: ComponentKind) -> str:
    """The hint shown for an empty component; only containers and galleries can be empty."""
    if kind not in (ComponentKind.CONTAINER, ComponentKind.MEDIA_GALLERY):
        return ""
    return t(language, f"info.kinds.{kind.value}.empty")
