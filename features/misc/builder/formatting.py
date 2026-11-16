from core.enums.language import SupportedLanguage


def format_number(language: SupportedLanguage, number: int) -> str:
    """`4000` -> `4.000` (German) / `4,000` (English)."""
    text = f"{number:,}"
    return text.replace(",", ".") if language is SupportedLanguage.GERMAN else text
