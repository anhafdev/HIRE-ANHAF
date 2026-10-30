from __future__ import annotations

import argparse
import asyncio
import json
import sys
from decimal import Decimal

from .config import Config
from .models import Network
from .verifier import DepositVerifier

NETWORK_ALIASES = {
    "btc": Network.BTC,
    "bitcoin": Network.BTC,
    "trc20": Network.USDT_TRC20,
    "usdt_trc20": Network.USDT_TRC20,
    "tron": Network.USDT_TRC20,
    "bep20": Network.USDT_BEP20,
    "usdt_bep20": Network.USDT_BEP20,
    "bsc": Network.USDT_BEP20,
    "eth": Network.ETH,
    "ethereum": Network.ETH,
    "erc20": Network.USDT_ERC20,
    "usdt_erc20": Network.USDT_ERC20,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cryptoverify", description="Verify a crypto deposit by transaction hash")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="verify one transaction")
    check.add_argument("--network", required=True, choices=sorted(NETWORK_ALIASES))
    check.add_argument("--txid", required=True)
    check.add_argument("--amount", required=True)
    check.add_argument("--invoice", default="CLI-CHECK")
    check.add_argument("--env", default=".env")
    check.add_argument("--json", action="store_true")

    identify = commands.add_parser("identify", help="tell which chain and asset a transaction hash is")
    identify.add_argument("--txid", required=True)
    identify.add_argument("--env", default=".env")

    health = commands.add_parser("health", help="show provider status per network")
    health.add_argument("--env", default=".env")

    pay = commands.add_parser("pay", help="interactive checkout: pick method, amount, pay, submit hash")
    pay.add_argument("--env", default=".env")

    return parser


async def run_check(args: argparse.Namespace) -> int:
    verifier = DepositVerifier(Config.from_env(args.env))
    async with verifier:
        result = await verifier.verify(
            txid=args.txid,
            network=NETWORK_ALIASES[args.network],
            expected_amount=Decimal(args.amount),
            invoice_id=args.invoice,
            invoice_created_at=None,
        )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"status         {result.status.value}")
        print(f"code           {result.code}")
        print(f"amount         {result.amount}")
        print(f"confirmations  {result.confirmations}/{result.required_confirmations}")
        print(f"provider       {result.provider_used}")
        print(f"message        {result.message}")
    return 0 if result.is_acceptable() else 1


async def run_identify(args: argparse.Namespace) -> int:
    from .checkout_models import NETWORK_LABELS, confirmations_text, display_amount

    verifier = DepositVerifier(Config.from_env(args.env))
    async with verifier:
        identity = await verifier.identify(args.txid)
    menu = verifier.config.enabled_networks()
    if not identity.found_on:
        probed = ", ".join(item.value for item in identity.probed) or "no enabled network"
        print(f"Not found on: {probed}")
        for failure in identity.provider_errors:
            print(f"  {failure.as_text()}")
        return 1
    for movement in identity.found_on:
        option = f"menu option {menu.index(movement.network) + 1}" if movement.network in menu else "not on the menu"
        pays = "pays our address" if movement.pays_us else "pays another address"
        print(
            f"{NETWORK_LABELS[movement.network]}: {display_amount(movement.amount)} {movement.asset}, {pays}, "
            f"confirmations {confirmations_text(movement.confirmations, movement.required_confirmations)}, {option}"
        )
    return 0 if any(item.pays_us for item in identity.found_on) else 1


async def run_health(args: argparse.Namespace) -> int:
    verifier = DepositVerifier(Config.from_env(args.env))
    async with verifier:
        report = await verifier.health()
    print(json.dumps(report, indent=2))
    return 0


async def run_pay(args: argparse.Namespace) -> int:
    from .interactive import run_wizard

    return await run_wizard(Config.from_env(args.env))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = {"check": run_check, "identify": run_identify, "health": run_health, "pay": run_pay}[args.command]
    try:
        return asyncio.run(runner(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
