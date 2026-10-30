from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import EMOJI, METHOD_LABELS


def btn(text: str, emoji: str, callback_data: str = None, url: str = None, style: str = "primary"):
    icon_id = EMOJI.get(emoji)
    has_icon = icon_id and icon_id != "YOUR_ID"
    return InlineKeyboardButton(
        text=text if has_icon else f"{emoji} {text}",
        callback_data=callback_data,
        url=url,
        icon_custom_emoji_id=icon_id if has_icon else None,
        style=style,
    )


def welcome_new():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Hire Me", "🔥", callback_data="hire_start", style="success")],
    ])


def welcome_active():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("My Status", "📋", callback_data="my_status", style="primary"),
            btn("Renew", "🔥", callback_data="hire_start", style="success"),
        ],
    ])


def welcome_pending():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Contact Support", "📩", url="https://t.me/anhafxd", style="primary")],
    ])


def plan_select():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("Daily", "🔥", callback_data="plan_daily", style="success"),
            btn("Weekly", "📅", callback_data="plan_weekly", style="success"),
            btn("Monthly", "⭐", callback_data="plan_monthly", style="danger"),
        ],
        [btn("Back", "◀️", callback_data="back_to_start", style="primary")],
    ])


def plan_daily_detail():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Continue with Daily", "🔥", callback_data="confirm_daily", style="success")],
        [btn("Back", "◀️", callback_data="hire_start", style="primary")],
    ])


def plan_weekly_detail():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Continue with Weekly", "🔥", callback_data="confirm_weekly", style="success")],
        [btn("Back", "◀️", callback_data="hire_start", style="primary")],
    ])


def plan_monthly_detail():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Continue with Monthly", "🔥", callback_data="confirm_monthly", style="danger")],
        [btn("Back", "◀️", callback_data="hire_start", style="primary")],
    ])


def payment_method(plan_key: str, methods: list[str]):
    rows = []
    row = []
    for index, method in enumerate(methods):
        style = "success" if index % 2 == 0 else "danger"
        row.append(btn(METHOD_LABELS[method], "🔗", callback_data=f"pay_{method}", style=style))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([btn("Back", "◀️", callback_data=f"plan_{plan_key}", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def wallet_info(plan_key: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("I've Paid · Submit TxID", "✅", callback_data="submit_txid", style="success")],
        [btn("Back", "◀️", callback_data=f"pay_method_{plan_key}", style="primary")],
    ])


def cancel_txid():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Cancel", "❌", callback_data="cancel_txid", style="danger")],
    ])


def try_again():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Try Again", "🔥", callback_data="hire_start", style="success")],
    ])


def renew_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Renew Plan", "🔥", callback_data="hire_start", style="success")],
    ])


def admin_confirm_reject(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("Confirm", "✅", callback_data=f"admin_confirm_{user_id}", style="success"),
            btn("Reject", "❌", callback_data=f"admin_reject_{user_id}", style="danger"),
        ],
    ])


def admin_active_list(user_ids_usernames):
    rows = [
        [btn(f"@{username}", "👤", callback_data=f"admin_user_{user_id}", style="primary")]
        for user_id, username in user_ids_usernames
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_detail(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            btn("Revoke", "❌", callback_data=f"admin_revoke_{user_id}", style="danger"),
            btn("Extend", "📅", callback_data=f"admin_extend_{user_id}", style="primary"),
            btn("Message", "📩", callback_data=f"admin_message_{user_id}", style="primary"),
        ],
        [btn("Back", "◀️", callback_data="admin_active_list", style="primary")],
    ])


def admin_cancel_broadcast():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("Cancel", "❌", callback_data="admin_cancel_broadcast", style="danger")],
    ])


def admin_settings_menu(demo_on: bool):
    label = "Demo Mode: ON → Turn OFF" if demo_on else "Demo Mode: OFF → Turn ON"
    style = "danger" if demo_on else "success"
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn(label, "🧪", callback_data="admin_toggle_demo", style=style)],
        [btn("Set Daily Price", "🔥", callback_data="admin_set_daily_amount", style="primary")],
    ])
