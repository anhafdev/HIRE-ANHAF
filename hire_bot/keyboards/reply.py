from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import EMOJI


def kbtn(text: str, emoji: str, style: str = "primary"):
    icon_id = EMOJI.get(emoji)
    has_icon = icon_id and icon_id != "YOUR_ID"
    return KeyboardButton(
        text=text if has_icon else f"{emoji} {text}",
        icon_custom_emoji_id=icon_id if has_icon else None,
        style=style,
    )


def admin_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [kbtn("Dashboard", "📊", style="primary"), kbtn("Users", "👥", style="primary")],
            [kbtn("Pending", "🕐", style="danger"), kbtn("Active", "✅", style="success")],
            [kbtn("Broadcast", "📩", style="primary"), kbtn("Settings", "⚙️", style="primary")],
        ],
        resize_keyboard=True,
    )
