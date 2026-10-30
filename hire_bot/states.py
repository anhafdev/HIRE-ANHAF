from aiogram.fsm.state import State, StatesGroup


class HireStates(StatesGroup):
    plan_select = State()
    payment_select = State()
    awaiting_txid = State()


class AdminStates(StatesGroup):
    awaiting_broadcast = State()
    awaiting_message = State()
    awaiting_daily_amount = State()
