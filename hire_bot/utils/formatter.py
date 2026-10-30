from datetime import datetime

from config import EMOJI


def e(emoji: str) -> str:
    emoji_id = EMOJI.get(emoji, "")
    if not emoji_id or emoji_id == "YOUR_ID":
        return emoji
    return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'


def fmt_date(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return "—"
    return value.strftime("%d %b %Y")


def fmt_datetime(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return "—"
    return value.strftime("%d %b %Y · %H:%M")
