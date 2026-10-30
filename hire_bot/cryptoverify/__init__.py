from __future__ import annotations

from decimal import Decimal

from .checkout import CheckoutSession, CheckoutStep, PaymentRequest, new_invoice_id
from .checkout_models import AcceptedOption
from .codes import Code, advice_for
from .config import Config
from .exceptions import ConfigurationError, CryptoVerifyError
from .models import (
    ChainTransaction,
    Network,
    ProviderError,
    Tier,
    TokenTransfer,
    VerifyResult,
    VerifyStatus,
)
from .networks.decoding import scale_units
from .pricing import PriceQuote
from .receipt import Receipt, build_receipt
from .resolve import AssetMovement, HashIdentity
from .storage import MemoryStorage, SQLiteStorage, StorageBackend, build_storage
from .verifier import DepositVerifier

__version__ = "1.0.0"


def _amounts_stay_exact() -> None:
    sample = scale_units(123456789, 8)
    if not isinstance(sample, Decimal):
        raise CryptoVerifyError("amount scaling must return Decimal, float path detected")
    if sample != Decimal("1.23456789"):
        raise CryptoVerifyError("amount scaling lost precision, float path detected")


_amounts_stay_exact()

__all__ = [
    "AcceptedOption",
    "AssetMovement",
    "HashIdentity",
    "ChainTransaction",
    "CheckoutSession",
    "CheckoutStep",
    "PaymentRequest",
    "Code",
    "Config",
    "ConfigurationError",
    "CryptoVerifyError",
    "DepositVerifier",
    "MemoryStorage",
    "Network",
    "PriceQuote",
    "ProviderError",
    "Receipt",
    "build_receipt",
    "SQLiteStorage",
    "StorageBackend",
    "Tier",
    "TokenTransfer",
    "VerifyResult",
    "VerifyStatus",
    "advice_for",
    "build_storage",
    "new_invoice_id",
    "__version__",
]
