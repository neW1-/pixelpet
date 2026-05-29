from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .config import RuntimeConfig, default_assets_dir, load_config, merge_overrides
from .codex_state import CodexStateReader
from .daemon import PixelPetDaemon
from .led_driver import DisplayError, DryRunDisplay, PixelDisplay
from .pet_pack import PetPackError, create_pet_pack, list_pets, load_pet
from .status import REQUIRED_STATUSES, Status


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except PetPackError as exc:
        parser.exit(2, f"pixelpet: {exc}\n")
    except DisplayError as exc:
        parser.exit(2, f"pixelpet: {exc}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pixelpet")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run the status daemon.")
    add_common_config_flags(run)
    run.add_argument("--address", help="Bluetooth address of the iPixel display.")
    run.add_argument("--brightness", type=int, help="Fixed display brightness.")
    run.add_argument("--pet", dest="pet_id", help="Pet id to use.")
    run.add_argument("--assets-dir", type=Path, help="Directory containing pet packs.")
    run.add_argument("--codex-home", type=Path, help="Codex home directory.")
    run.add_argument("--poll-seconds", type=float, help="Polling interval.")
    run.add_argument("--done-timeout-seconds", type=float, help="How long done stays visible.")
    run.add_argument("--dry-run", action="store_true", help="Print status changes without display hardware.")
    run.add_argument("--once", action="store_true", help="Send one status GIF and exit.")
    run.set_defaults(func=run_daemon)

    status = subparsers.add_parser("status", help="Print the current inferred Codex status once.")
    add_common_config_flags(status)
    status.add_argument("--codex-home", type=Path, help="Codex home directory.")
    status.add_argument("--done-timeout-seconds", type=float, help="How long done stays visible.")
    status.set_defaults(func=print_status)

    show = subparsers.add_parser("show", help="Send one explicit status GIF and exit.")
    add_common_config_flags(show)
    show.add_argument("status", choices=[status.value for status in REQUIRED_STATUSES])
    show.add_argument("--address", help="Bluetooth address of the iPixel display.")
    show.add_argument("--brightness", type=int, help="Fixed display brightness.")
    show.add_argument("--pet", dest="pet_id", help="Pet id to use.")
    show.add_argument("--assets-dir", type=Path, help="Directory containing pet packs.")
    show.add_argument("--dry-run", action="store_true", help="Print the GIF path without display hardware.")
    show.set_defaults(func=show_explicit_status)

    scan = subparsers.add_parser("scan", help="Scan for nearby BLE devices.")
    scan.add_argument("--timeout", type=float, default=5.0)
    scan.set_defaults(func=scan_devices)

    pets = subparsers.add_parser("pets", help="Manage LED pet packs.")
    pets_sub = pets.add_subparsers(dest="pets_command", required=True)

    pets_list = pets_sub.add_parser("list", help="List available pets.")
    pets_list.add_argument("--assets-dir", type=Path, default=default_assets_dir())
    pets_list.set_defaults(func=list_pet_packs)

    pets_validate = pets_sub.add_parser("validate", help="Validate a pet pack.")
    pets_validate.add_argument("pet_id")
    pets_validate.add_argument("--assets-dir", type=Path, default=default_assets_dir())
    pets_validate.add_argument("--skip-image-checks", action="store_true")
    pets_validate.set_defaults(func=validate_pet_pack)

    pets_create = pets_sub.add_parser("create", help="Create a new pet-pack skeleton.")
    pets_create.add_argument("pet_id")
    pets_create.add_argument("--display-name")
    pets_create.add_argument("--assets-dir", type=Path, default=default_assets_dir())
    pets_create.add_argument("--overwrite", action="store_true")
    pets_create.set_defaults(func=create_pet)

    return parser


def add_common_config_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, help="Config TOML path.")


def run_daemon(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    pet = load_pet(config.pet_id, config.assets_dir)
    pet.validate_or_raise(check_images=True)
    daemon = PixelPetDaemon.from_config(config, pet)
    if args.once:
        asyncio.run(daemon.run_once())
    else:
        asyncio.run(daemon.run_forever())
    return 0


def print_status(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    reader = CodexStateReader(
        codex_home=config.codex_home,
        done_timeout_seconds=config.done_timeout_seconds,
        active_window_seconds=config.active_window_seconds,
    )
    snapshot = reader.current_status()
    print(f"{snapshot.status.value}: {snapshot.reason}")
    return 0


def scan_devices(args: argparse.Namespace) -> int:
    async def _scan() -> None:
        try:
            from bleak import BleakScanner
        except ImportError as exc:
            raise RuntimeError("Install pypixelcolor or bleak before scanning.") from exc
        devices = await BleakScanner.discover(timeout=args.timeout)
        for device in devices:
            name = device.name or "(unnamed)"
            print(f"{device.address}\t{name}")

    asyncio.run(_scan())
    return 0


def show_explicit_status(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    pet = load_pet(config.pet_id, config.assets_dir)
    pet.validate_or_raise(check_images=True)
    status = Status(args.status)
    gif_path = pet.gif_for(status)

    async def _show() -> None:
        if config.dry_run:
            display = DryRunDisplay()
        else:
            if not config.address:
                raise DisplayError("Display address is required unless --dry-run is set.")
            display = PixelDisplay(config.address, brightness=config.brightness)
        await display.connect()
        try:
            await display.show_gif(gif_path)
        finally:
            await display.disconnect()

    asyncio.run(_show())
    print(f"status={status.value} gif={gif_path}")
    return 0


def list_pet_packs(args: argparse.Namespace) -> int:
    pets = list_pets(args.assets_dir)
    if not pets:
        print("No pet packs found.")
        return 0
    for pet in pets:
        print(f"{pet.pet_id}\t{pet.display_name}\t{pet.root}")
    return 0


def validate_pet_pack(args: argparse.Namespace) -> int:
    pet = load_pet(args.pet_id, args.assets_dir)
    errors = pet.validate(check_images=not args.skip_image_checks)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1
    print(f"{pet.pet_id} is valid.")
    return 0


def create_pet(args: argparse.Namespace) -> int:
    root = create_pet_pack(
        args.pet_id,
        display_name=args.display_name,
        assets_dir=args.assets_dir,
        overwrite=args.overwrite,
    )
    print(root)
    return 0


def _config_from_args(args: argparse.Namespace) -> RuntimeConfig:
    config = load_config(args.config)
    overrides = {
        "address": getattr(args, "address", None),
        "brightness": getattr(args, "brightness", None),
        "pet_id": getattr(args, "pet_id", None),
        "assets_dir": getattr(args, "assets_dir", None),
        "codex_home": getattr(args, "codex_home", None),
        "poll_seconds": getattr(args, "poll_seconds", None),
        "done_timeout_seconds": getattr(args, "done_timeout_seconds", None),
        "dry_run": True if getattr(args, "dry_run", False) else None,
    }
    return merge_overrides(config, **overrides)


if __name__ == "__main__":
    raise SystemExit(main())
