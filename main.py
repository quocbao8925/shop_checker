"""Main Entry Point and CLI for Valorant Shop Android Tool.

Can be run directly via CLI to test on desktop, or loaded as a module.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from manager import ValorantShopManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def cmd_status(manager: ValorantShopManager) -> None:
    print("\n--- Session & Cache Status ---")
    if manager.is_authenticated:
        tokens = manager.current_tokens
        print("Status: AUTHENTICATED")
        print(f"PUUID:  {tokens.puuid if tokens else 'N/A'}")
        print(f"Region: {tokens.region if tokens else 'N/A'}")
        print(f"Shard:  {tokens.shard if tokens else 'N/A'}")
    else:
        print("Status: NOT AUTHENTICATED")

    version = manager.cache.get_client_version()
    print(f"Cached Client Version: {version or 'None (run sync)'}")
    print(f"Assets In Database:    {'Yes' if manager.cache.has_assets() else 'No'}")
    print("------------------------------\n")


def cmd_sync(manager: ValorantShopManager) -> None:
    print("Synchronizing weapon skins, tiers, bundles, and version from valorant-api.com...")
    version = manager.initialize_assets(force=True)
    print(f"Asset synchronization complete! Client version: {version}")


def cmd_login(manager: ValorantShopManager) -> None:
    url = manager.get_login_url()
    print("\n=== Riot Login Required ===")
    print("1. Open the following URL in your web browser:")
    print(f"\n   {url}\n")
    print("2. Sign in with your Riot Account.")
    print("3. When you see the 'can't connect' error page (redirecting to localhost),")
    print("   copy the FULL address bar URL and run:")
    print("   python main.py auth")
    print("4. Paste the full redirect URL at the hidden prompt.\n")


def cmd_auth(manager: ValorantShopManager, url: str | None = None) -> None:
    if not url:
        url = getpass.getpass("Paste the full Riot redirect URL (input hidden): ").strip()
    if not url:
        print("Authentication cancelled: no redirect URL was provided.")
        return

    print("Authenticating with Riot servers...")
    tokens = manager.login_with_url(url)
    print("Authentication successful!")
    print(f"PUUID:  {tokens.puuid}")
    print(f"Region: {tokens.region}")
    print(f"Shard:  {tokens.shard}")


def cmd_shop(manager: ValorantShopManager) -> None:
    if not manager.is_authenticated:
        print("Error: You are not logged in. Run 'login' first.")
        sys.exit(1)

    print("Fetching store data...")
    snapshot = manager.get_shop_data()

    print("\n================== WALLET ==================")
    print(f"VP: {snapshot.wallet.valorant_points} | Radianite: {snapshot.wallet.radianite_points}")

    print("\n================ DAILY STORE ===============")
    hours = snapshot.daily_store.seconds_remaining // 3600
    mins = (snapshot.daily_store.seconds_remaining % 3600) // 60
    print(f"Time Remaining: {hours}h {mins}m")
    print("--------------------------------------------")
    for offer in snapshot.daily_store.offers:
        print(f"  - {offer.name:<32} {offer.cost:>5} VP  [{offer.content_tier_name}]")

    if snapshot.bundles:
        print("\n============= FEATURED BUNDLES =============")
        for bundle in snapshot.bundles:
            print(f"  * {bundle.name} (Discounted: {bundle.total_discounted_price} VP)")
            for item in bundle.items:
                print(f"     > {item.name:<30} {item.discounted_price:>5} VP")
    print("============================================\n")


def cmd_mock(manager: ValorantShopManager) -> None:
    """Run a simulated shop check using local sample data (no Riot login required)."""
    print("Running simulated shop check using local asset database...")
    manager.initialize_assets()

    # Sample storefront payload structure
    mock_storefront = {
        "SkinsPanelLayout": {
            "SingleItemStoreOffers": [
                {
                    "OfferID": "3e0bf03b-4833-2895-e236-47a829e0000a",
                    "Cost": {"85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741": 1775},
                    "Rewards": [{"ItemID": "3e0bf03b-4833-2895-e236-47a829e0000a"}],
                },
                {
                    "OfferID": "7ed9f579-45cb-fb5a-e455-879e6fae85df",
                    "Cost": {"85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741": 1775},
                    "Rewards": [{"ItemID": "7ed9f579-45cb-fb5a-e455-879e6fae85df"}],
                },
                {
                    "OfferID": "29d2b7d4-4158-9a99-8cf0-2184b2db0a61",
                    "Cost": {"85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741": 2375},
                    "Rewards": [{"ItemID": "29d2b7d4-4158-9a99-8cf0-2184b2db0a61"}],
                },
                {
                    "OfferID": "c36ff63d-4c37-83d3-7393-279c138f36a8",
                    "Cost": {"85ad13f7-3d1b-5128-9eb2-7cd8ee0b5741": 1775},
                    "Rewards": [{"ItemID": "c36ff63d-4c37-83d3-7393-279c138f36a8"}],
                },
            ],
            "SingleItemOffersRemainingDurationInSeconds": 48200,
        },
        "FeaturedBundle": {
            "Bundles": [
                {
                    "DataAssetID": "3b60383b-483c-62bb-f5d6-d08ec42b0db2",
                    "DurationRemainingInSeconds": 345600,
                    "Items": [
                        {
                            "Item": {"ItemID": "29d2b7d4-4158-9a99-8cf0-2184b2db0a61"},
                            "BasePrice": 2375,
                            "DiscountedPrice": 2375,
                            "DiscountPercent": 0.0,
                        }
                    ],
                }
            ]
        },
    }

    daily = manager.store_client.parse_daily_store(mock_storefront)
    bundles = manager.store_client.parse_bundles(mock_storefront)
    from models import StoreSnapshot, Wallet
    wallet = Wallet(valorant_points=2450, radianite_points=120)

    snapshot = StoreSnapshot(daily_store=daily, bundles=bundles, wallet=wallet)
    manager.cache.save_store_snapshot(snapshot)

    print("\n================== WALLET ==================")
    print(f"VP: {snapshot.wallet.valorant_points} | Radianite: {snapshot.wallet.radianite_points}")

    print("\n================ DAILY STORE ===============")
    hours = snapshot.daily_store.seconds_remaining // 3600
    mins = (snapshot.daily_store.seconds_remaining % 3600) // 60
    print(f"Time Remaining: {hours}h {mins}m")
    print("--------------------------------------------")
    for offer in snapshot.daily_store.offers:
        print(f"  - {offer.name:<28} {offer.cost:>5} VP  [{offer.content_tier_name}]")

    if snapshot.bundles:
        print("\n============= FEATURED BUNDLES =============")
        for bundle in snapshot.bundles:
            print(f"  * {bundle.name} (Duration: {bundle.duration_remaining_secs // 86400}d left)")
            for item in bundle.items:
                print(f"     > {item.name:<26} {item.discounted_price:>5} VP")
    print("============================================\n")


def cmd_logout(manager: ValorantShopManager) -> None:
    manager.logout()
    print("Logged out successfully. Session tokens cleared.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Valorant Shop Android Tool CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="Check login status and cache info")
    subparsers.add_parser("sync", help="Fetch skins and assets from valorant-api.com")
    subparsers.add_parser("mock", help="Run simulated shop display without login")
    subparsers.add_parser("login", help="Show Riot OAuth authorization URL")

    auth_parser = subparsers.add_parser("auth", help="Complete login with pasted redirect URL")
    auth_parser.add_argument(
        "url",
        nargs="?",
        help="Full redirect URL containing access_token (omit to paste securely)",
    )

    subparsers.add_parser("shop", help="Display daily store, bundles, and wallet")
    subparsers.add_parser("logout", help="Log out and clear stored session")

    args = parser.parse_args()

    manager = ValorantShopManager()
    try:
        if args.command == "status" or not args.command:
            cmd_status(manager)
        elif args.command == "sync":
            cmd_sync(manager)
        elif args.command == "mock":
            cmd_mock(manager)
        elif args.command == "login":
            cmd_login(manager)
        elif args.command == "auth":
            cmd_auth(manager, args.url)
        elif args.command == "shop":
            cmd_shop(manager)
        elif args.command == "logout":
            cmd_logout(manager)
        else:
            parser.print_help()
    finally:
        manager.close()


if __name__ == "__main__":
    main()
