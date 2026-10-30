import os
from dotenv import load_dotenv

from cryptoverify import Config as CryptoverifyConfig, Network

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8256044823"))
ADMIN_USERNAME = "anhafxd"

CHECKOUT_EXPIRY_MINUTES = 60

CV_CONFIG = CryptoverifyConfig.from_env()

NETWORK_BY_METHOD = {
    "btc": Network.BTC,
    "trc20": Network.USDT_TRC20,
    "bep20": Network.USDT_BEP20,
    "eth": Network.ETH,
    "erc20": Network.USDT_ERC20,
}
METHOD_BY_NETWORK = {network: method for method, network in NETWORK_BY_METHOD.items()}

METHOD_ORDER = ["btc", "bep20", "trc20", "eth", "erc20"]

METHOD_LABELS = {
    "btc": "Bitcoin",
    "bep20": "USDT-BEP20",
    "trc20": "USDT-TRC20",
    "eth": "Ethereum",
    "erc20": "USDT-ERC20",
}

METHOD_EXPLORERS = {
    "btc": ("blockchain.com", "search your transaction → copy the Transaction Hash shown at the top."),
    "bep20": ("bscscan.com", "search your wallet address → find the transaction → copy the TxHash."),
    "trc20": ("tronscan.org", "search your wallet address → find the transaction → copy the Transaction Hash (starts with a long hex string)."),
    "eth": ("etherscan.io", "search your wallet address → find the transaction → copy the Transaction Hash."),
    "erc20": ("etherscan.io", "search your wallet address → find the transaction → copy the Transaction Hash."),
}


def enabled_methods() -> list[str]:
    live = set(CV_CONFIG.enabled_networks())
    return [method for method in METHOD_ORDER if NETWORK_BY_METHOD[method] in live]


PLANS = {
    "daily": {
        "label": "Daily",
        "amount": 25,
        "days": 1,
        "remind_before": 0,
    },
    "weekly": {
        "label": "Weekly",
        "amount": 70,
        "days": 7,
        "remind_before": 2,
    },
    "monthly": {
        "label": "Monthly",
        "amount": 300,
        "days": 30,
        "remind_before": 5,
    },
}

DASHBOARD_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "image.png")

EMOJI = {
    "👑": "5271557007009128936",
    "⚡": "5220195537520711716",
    "✅": "6088971806939550947",
    "🔥": "5256047523620995497",
    "🔒": "5285025324369717626",
    "💼": "5334708741545680612",
    "🕐": "5445010743021818722",
    "🔔": "5451927229506268442",
    "🛡️": "5285087932107989972",
    "📅": "5413879192267805083",
    "📊": "6001546944470587024",
    "🔍": "5231012545799666522",
    "⚠️": "5945169653260095496",
    "⭐": "4958714479681471536",
    "💻": "5321154224191462061",
    "🌐": "5999317873623831250",
    "🏷️": "5298877105000439431",
    "➡️": "5409088413947157071",
    "👤": "5249053508681883137",
    "📩": "5472239203590888751",
    "👥": "5453957997418004470",
    "🎁": "5199749070830197566",
    "ℹ️": "5334544901428229844",
    "💰": "5899842131786209184",
    "🔗": "6059958456746511855",
    "📋": "5926993166979831323",
    "🧪": "5258208871423425369",
    "❌": "5348027250446967673",
    "◀️": "5256247952564825322",
    "💳": "5445353829304387411",
    "⚙️": "5260343246831237239",
}
