from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .activity import record_activity
from .backup import backup_state, restore_state
from .bookmark_import import ImportFilters, find_duplicate_groups, import_bookmarks
from .browser_scan import scan_browser_bookmarks
from .config import load_config
from .database import init_db
from .installer import (
    detect_vault_path,
    doctor,
    install_worker_startup,
    install_native_manifest,
    open_extension_setup,
    write_config,
    write_native_manifest,
)
from .native_host import run_native_host
from .service import ingest_bookmark_event
from .worker import run_worker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bookmark-agent")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Initialize SQLite schema")
    subparsers.add_parser("native-host", help="Run Native Messaging host on stdio")
    subparsers.add_parser("native-command", help="Print the native host command helper")
    shim = subparsers.add_parser("create-native-shim", help="Create a Windows .cmd shim for Native Messaging")
    shim.add_argument("--output", default="native-host/bookmark-agent-native.cmd", help="Output .cmd path")

    worker_shim = subparsers.add_parser("create-worker-shim", help="Create a Windows .cmd shim for the worker")
    worker_shim.add_argument("--output", default="outputs/bookmark-agent-worker.cmd", help="Output .cmd path")

    init_config = subparsers.add_parser("init-config", help="Create config.toml")
    init_config.add_argument("--vault-path", help="Absolute Obsidian vault path. Defaults to detected D: vault.")
    init_config.add_argument("--force", action="store_true", help="Overwrite existing config")

    install_host = subparsers.add_parser("install-native-host", help="Write native host manifest and HKCU registry key")
    install_host.add_argument("--browser", choices=["chrome", "firefox"], required=True)
    install_host.add_argument("--host-path", default="outputs/bookmark-agent-native.exe")
    install_host.add_argument("--manifest-dir", default="outputs")
    install_host.add_argument("--chrome-extension-id", help="Required for Chrome after loading unpacked extension")

    startup = subparsers.add_parser("install-worker-startup", help="Register worker shim in HKCU startup")
    startup.add_argument("--command-path", default="outputs/bookmark-agent-worker.cmd")

    simulate = subparsers.add_parser("simulate-event", help="Insert one bookmark event into SQLite for diagnostics")
    simulate.add_argument("--url", default="https://example.com/?utm_source=test&a=1#section")
    simulate.add_argument("--title", default="Example Bookmark")
    simulate.add_argument("--browser", default="diagnostic")

    subparsers.add_parser("doctor", help="Check local setup")
    subparsers.add_parser("test-notification", help="Write one activity entry and show a desktop notification")
    backup_parser = subparsers.add_parser("backup", help="Create a Pro app-state backup")
    backup_parser.add_argument("--output", required=True, help="Destination .zip path")
    restore_parser = subparsers.add_parser("restore", help="Restore a Pro app-state backup")
    restore_parser.add_argument("--input", required=True, help="Backup .zip path")
    duplicate_parser = subparsers.add_parser("duplicate-report", help="Create a Pro duplicate bookmark report")
    duplicate_parser.add_argument("--browser", choices=["chrome", "firefox"], help="Filter scanned browser source")
    duplicate_parser.add_argument("--profile", help="Filter profile name substring")
    duplicate_parser.add_argument("--folder", help="Filter folder path/title substring")
    duplicate_parser.add_argument("--domain", help="Filter domain substring")
    duplicate_parser.add_argument("--url-contains", help="Filter URL substring")
    duplicate_parser.add_argument("--type", choices=["webpage", "youtube"], dest="resource_type")
    subparsers.add_parser("open-extension-setup", help="Open browser extension pages and outputs folder")
    scan = subparsers.add_parser("scan-bookmarks", help="Scan local Chrome/Firefox bookmark stores once")
    scan.add_argument("--dry-run", action="store_true", help="Count changes without enqueueing events")
    scan.add_argument("--mark-seen", action="store_true", help="Save current scan state without enqueueing old bookmarks")

    import_parser = subparsers.add_parser("import-bookmarks", help="Import existing browser bookmarks")
    import_parser.add_argument("--mode", choices=["summarize"], default="summarize")
    import_parser.add_argument("--dry-run", action="store_true", help="Preview without enqueueing summaries")
    import_parser.add_argument("--browser", choices=["chrome", "firefox"], help="Filter scanned browser source")
    import_parser.add_argument("--profile", help="Filter profile name substring")
    import_parser.add_argument("--folder", help="Filter folder path/title substring")
    import_parser.add_argument("--domain", help="Filter domain substring, for example youtube.com")
    import_parser.add_argument("--url-contains", help="Filter URL substring")
    import_parser.add_argument("--type", choices=["webpage", "youtube"], dest="resource_type", help="Filter resource type")
    import_parser.add_argument("--limit", type=int, help="Maximum selected bookmarks")
    import_parser.add_argument("--all", action="store_true", help="Allow summarize mode without --limit")

    worker = subparsers.add_parser("worker", help="Run processing worker")
    worker.add_argument("--once", action="store_true", help="Process one batch and exit")
    worker.add_argument("--sleep-seconds", type=int, default=10, help="Worker polling interval")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_path = Path(args.config).resolve()

    if args.command == "native-command":
        print(f"{Path(sys.executable).resolve()} -m bookmark_agent.cli --config {config_path} native-host")
        return 0

    if args.command == "create-native-shim":
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "@echo off\r\n"
            f"\"{Path(sys.executable).resolve()}\" -m bookmark_agent.cli --config \"{config_path}\" native-host\r\n"
        )
        output.write_text(script, encoding="utf-8")
        print(f"Created native messaging shim: {output}")
        return 0

    if args.command == "create-worker-shim":
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        script = (
            "@echo off\r\n"
            f"cd /d \"{config_path.parent}\"\r\n"
            f"\"{Path(sys.executable).resolve()}\" -m bookmark_agent.cli --config \"{config_path}\" worker\r\n"
        )
        output.write_text(script, encoding="utf-8")
        print(f"Created worker shim: {output}")
        return 0

    if args.command == "init-config":
        vault_path = Path(args.vault_path).resolve() if args.vault_path else detect_vault_path()
        if not vault_path:
            raise SystemExit("Could not auto-detect a D: Obsidian vault. Re-run with --vault-path D:\\path\\to\\vault")
        write_config(config_path, vault_path, force=args.force)
        print(f"Created config: {config_path}")
        print(f"Vault path: {vault_path}")
        return 0

    config = load_config(config_path)

    if args.command in {"backup", "restore", "duplicate-report"} and not config.features.pro_enabled:
        raise SystemExit(f"{args.command} is a Pro feature. Use the subscription-enabled desktop app.")

    if args.command == "backup":
        init_db(config.database.path)
        print(json.dumps(backup_state(config, Path(args.output)), ensure_ascii=False, indent=2))
        return 0

    if args.command == "restore":
        init_db(config.database.path)
        print(json.dumps(restore_state(config, Path(args.input)), ensure_ascii=False, indent=2))
        return 0

    if args.command == "duplicate-report":
        filters = ImportFilters(
            browser=args.browser,
            profile=args.profile,
            folder=args.folder,
            domain=args.domain,
            url_contains=args.url_contains,
            resource_type=args.resource_type,
        )
        print(json.dumps({"ok": True, "groups": find_duplicate_groups(filters)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "init-db":
        init_db(config.database.path)
        print(f"Initialized database: {config.database.path}")
        return 0

    if args.command == "native-host":
        init_db(config.database.path)
        run_native_host(config)
        return 0

    if args.command == "worker":
        init_db(config.database.path)
        try:
            run_worker(config, once=args.once, sleep_seconds=args.sleep_seconds)
        except RuntimeError as error:
            if "Another worker is already running" in str(error):
                print(str(error))
                return 0
            raise
        return 0

    if args.command == "install-native-host":
        host_path = Path(args.host_path).resolve()
        if not host_path.exists():
            raise SystemExit(f"Native host executable does not exist: {host_path}")
        manifest_path = write_native_manifest(
            args.browser,
            host_path,
            Path(args.manifest_dir).resolve(),
            chrome_extension_id=args.chrome_extension_id,
        )
        registry_key = install_native_manifest(args.browser, manifest_path)
        print(f"Wrote manifest: {manifest_path}")
        print(f"Registered: {registry_key}")
        return 0

    if args.command == "install-worker-startup":
        command_path = Path(args.command_path).resolve()
        if not command_path.exists():
            raise SystemExit(f"Worker command does not exist: {command_path}")
        registry_key = install_worker_startup(command_path)
        print(f"Registered worker startup: {registry_key}")
        return 0

    if args.command == "simulate-event":
        init_db(config.database.path)
        result = ingest_bookmark_event(
            config,
            {
                "schema_version": 1,
                "source": {"browser": args.browser, "extension": "diagnostic"},
                "event": {"type": "created"},
                "bookmark": {
                    "id": "diagnostic-1",
                    "parentId": "diagnostic",
                    "title": args.title,
                    "url": args.url,
                },
                "change": {},
            },
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "scan-bookmarks":
        init_db(config.database.path)
        result = scan_browser_bookmarks(config, dry_run=args.dry_run or args.mark_seen, mark_seen=args.mark_seen)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "import-bookmarks":
        init_db(config.database.path)
        if not config.features.pro_enabled:
            raise SystemExit("Existing bookmark bulk analysis is a Pro feature. Use the subscription-enabled desktop app.")
        if args.mode == "summarize" and args.limit is None and not args.all and not args.dry_run:
            raise SystemExit("summarize mode can enqueue many jobs. Use --limit N or --all.")
        filters = ImportFilters(
            browser=args.browser,
            profile=args.profile,
            folder=args.folder,
            domain=args.domain,
            url_contains=args.url_contains,
            resource_type=args.resource_type,
            limit=args.limit,
        )
        result = import_bookmarks(config, args.mode, filters, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "doctor":
        init_db(config.database.path)
        results = doctor(config, Path.cwd().resolve())
        failed = 0
        for result in results:
            status = "OK" if result.ok else "WARN"
            print(f"[{status}] {result.name}: {result.detail}")
            if not result.ok:
                failed += 1
        print(f"Doctor finished with {failed} warning(s).")
        return 0

    if args.command == "test-notification":
        record_activity(
            config,
            "notification_test",
            "Bookmark Agent notification test",
            f"Notifications are enabled. {config.summarizer.provider} model: {config.summarizer.model}.",
            details={"provider": config.summarizer.provider, "model": config.summarizer.model},
            notify=True,
        )
        print("Wrote activity entry and requested desktop notification.")
        return 0

    if args.command == "open-extension-setup":
        opened = open_extension_setup(Path.cwd().resolve())
        chrome_id_path = Path.cwd().resolve() / "outputs" / "chrome-extension-id.txt"
        chrome_extension_id = chrome_id_path.read_text(encoding="utf-8").strip() if chrome_id_path.exists() else "unknown"
        print("Opened setup targets:")
        for item in opened:
            print(f"- {item}")
        print("Chrome extension folder: outputs\\chrome-extension")
        print(f"Chrome extension ID: {chrome_extension_id}")
        print("Firefox manifest: outputs\\firefox-extension\\manifest.json")
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
