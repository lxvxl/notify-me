#!/usr/bin/env python3
"""Send a personal notification using ~/.notify-me/config.json."""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


__version__ = "1.3.0"

AAD = b"notify-me sealed configuration v1"
DEFAULT_URL = "https://rosmontis.cc"
COMMAND_NAME = "notify-me"


class NotificationError(RuntimeError):
    pass


def config_path() -> Path:
    configured = os.environ.get("NOTIFY_ME_CONFIG", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".notify-me" / "config.json"


def base_url(raw: Mapping[str, object]) -> str:
    """Resolve the service URL: NOTIFY_ME_URL env var wins over config and default."""
    override = os.environ.get("NOTIFY_ME_URL", "").strip()
    if override:
        return override
    return string(raw, "base_url", DEFAULT_URL)


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.expanduser().read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise NotificationError(f"Config not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise NotificationError(f"Cannot read config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise NotificationError("Config must be a JSON object.")
    return value


def aesgcm() -> Any:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM
    except ImportError as exc:
        raise NotificationError("Install dependency: pipx install \"notify-me[crypto]\"") from exc


def decode(value: object, name: str) -> bytes:
    if not isinstance(value, str):
        raise NotificationError(f"Sealed config field '{name}' must be a base64 string.")
    try:
        return base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise NotificationError(f"Sealed config field '{name}' is invalid.") from exc


def seal(raw: Mapping[str, object], phrase: str) -> dict[str, object]:
    if not phrase:
        raise NotificationError("Passphrase must not be empty.")
    salt, nonce = os.urandom(16), os.urandom(12)
    key = hashlib.scrypt(phrase.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    ciphertext = aesgcm()(key).encrypt(nonce, json.dumps(raw, ensure_ascii=False, separators=(",", ":")).encode(), AAD)
    return {"version": 1, "kdf": {"name": "scrypt", "n": 16384, "r": 8, "p": 1},
            "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()}


def unseal(blob: Mapping[str, object], phrase: str) -> dict[str, object]:
    try:
        kdf = blob["kdf"]
        if blob.get("version") != 1 or not isinstance(kdf, Mapping) or kdf.get("name") != "scrypt":
            raise ValueError
        n, r, p = int(kdf["n"]), int(kdf["r"]), int(kdf["p"])
        if n < 2 or n & (n - 1) or r < 1 or p < 1:
            raise ValueError
        key = hashlib.scrypt(phrase.encode(), salt=decode(blob.get("salt"), "salt"), n=n, r=r, p=p, dklen=32)
        raw = json.loads(aesgcm()(key).decrypt(decode(blob.get("nonce"), "nonce"), decode(blob.get("ciphertext"), "ciphertext"), AAD).decode())
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationError("Could not unlock sealed config: wrong passphrase or altered data.") from exc
    if not isinstance(raw, dict):
        raise NotificationError("Unlocked config must be a JSON object.")
    return raw


def string(raw: Mapping[str, object], name: str, default: str) -> str:
    value = raw.get(name, default)
    if not isinstance(value, str):
        raise NotificationError(f"Config value '{name}' must be a string.")
    return value


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError as exc:
        raise NotificationError("Aborted: input stream ended.") from exc
    return answer or default


def build_config_interactively() -> dict[str, object]:
    print(f"Configuring {COMMAND_NAME} for {config_path()}.")
    print("Press Enter to accept the [default].")
    headers: dict[str, str] = {}
    print("\nHeaders sent with every request (e.g. Authorization). Leave the name empty to finish.")
    while True:
        name = input("  header name (empty to finish): ").strip()
        if not name:
            break
        value = input(f"  value for {name}: ").strip()
        if not value:
            print("  skipped (empty value).")
            continue
        if name in headers:
            print(f"  overwriting the previous value of {name}.")
        headers[name] = value
    if not headers:
        raise NotificationError("At least one header is required (the service needs authentication).")
    print()
    while True:
        channel = ask("Default channel (instant/bark)", "instant").lower()
        if channel in {"instant", "bark"}:
            break
        print("  Please choose 'instant' or 'bark'.")
    while True:
        source = ask("Default source", "notify-me")
        if source.strip() or channel != "instant":
            break
        print("  source is required for instant notifications.")
    base = ask("Service base URL", DEFAULT_URL).rstrip("/")
    config: dict[str, object] = {"headers": headers, "channel": channel, "source": source}
    if base and base != DEFAULT_URL.rstrip("/"):
        config["base_url"] = base
    return config


def send(text: str, title: str, channel: str | None, source: str | None, timeout: float | None) -> Any:
    raw = read_json(config_path())
    headers = raw.get("headers")
    if not isinstance(headers, dict) or not headers:
        raise NotificationError("Config must contain a non-empty 'headers' object.")
    target_channel = channel or string(raw, "channel", "instant")
    target_source = source if source is not None else string(raw, "source", "notify-me")
    if target_channel == "instant" and not target_source.strip():
        raise NotificationError("source is required for instant notifications.")
    try:
        request_timeout = timeout if timeout is not None else float(raw.get("timeout", 10))
    except (TypeError, ValueError) as exc:
        raise NotificationError("Config timeout must be numeric.") from exc
    payload: dict[str, str] = {"channel": target_channel, "text": text}
    if title:
        payload["title"] = title
    if target_channel == "instant":
        payload["source"] = target_source.strip()
    request_headers = {"Content-Type": "application/json", "Accept": "application/json",
                       "User-Agent": string(raw, "user_agent", f"{COMMAND_NAME}/{__version__}"),
                       "X-Device-Id": string(raw, "device_id", "python-script"),
                       "X-Device-Name": string(raw, "device_name", "Python Script"),
                       **{str(k): str(v) for k, v in headers.items()}}
    request = urllib.request.Request(base_url(raw).rstrip("/") + "/m/message_push/post_message",
        data=json.dumps(payload, ensure_ascii=False).encode(), headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=request_timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise NotificationError(f"Notification service returned HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise NotificationError(f"Notification request failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise NotificationError("Notification service returned non-JSON response.") from exc


def main() -> int:
    argv = sys.argv[1:]
    if not argv or (argv[0] not in {"send", "seal", "setup"} and not argv[0].startswith("-")):
        argv.insert(0, "send")
    parser = argparse.ArgumentParser(description="Send personal notifications.")
    parser.add_argument("--version", action="version", version=f"{COMMAND_NAME} {__version__}")
    sub = parser.add_subparsers(dest="command")
    send_parser = sub.add_parser("send")
    send_parser.add_argument("text", nargs="?")
    send_parser.add_argument("-t", "--title", default="")
    send_parser.add_argument("-s", "--source")
    send_parser.add_argument("-c", "--channel", choices=["instant", "bark"])
    send_parser.add_argument("--timeout", type=float)
    send_parser.add_argument("--json", action="store_true")
    seal_parser = sub.add_parser("seal")
    seal_parser.add_argument("input", type=Path)
    seal_parser.add_argument("output", type=Path)
    setup_parser = sub.add_parser("setup", help="create ~/.notify-me/config.json interactively, or unlock a sealed config")
    setup_parser.add_argument("sealed", type=Path, nargs="?", help="sealed file to unlock; omit to configure interactively")
    args = parser.parse_args(argv)
    try:
        if args.command == "seal":
            first, second = getpass.getpass("New notify-me passphrase: "), getpass.getpass("Repeat passphrase: ")
            if not first or first != second:
                raise NotificationError("Passphrases are empty or do not match.")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(seal(read_json(args.input), first), indent=2) + "\n", encoding="utf-8")
            os.chmod(args.output, 0o600)
            print(f"Wrote sealed config to {args.output}")
        elif args.command == "setup":
            destination = config_path()
            raw: dict[str, object]
            sealed_source: Path | None = None
            if args.sealed is None:
                if destination.exists() and ask(f"{destination} already exists. Overwrite?", "n").lower() not in {"y", "yes"}:
                    print("Kept the existing config untouched.")
                    return 0
                raw = build_config_interactively()
            else:
                sealed_source = args.sealed.expanduser()
                raw = unseal(read_json(sealed_source), getpass.getpass("notify-me passphrase: "))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.chmod(destination, 0o600)
            if sealed_source is not None:
                sealed_source.unlink()
            print(f"Saved config to {destination}")
            if args.sealed is None and ask("Send a test notification now?", "y").lower() in {"y", "yes"}:
                try:
                    send(ask("Test message", f"{COMMAND_NAME} is configured."), "", None, None, None)
                    print("Test notification sent.")
                except NotificationError as exc:
                    print(f"Test send failed, but the config was saved: {exc}", file=sys.stderr)
        else:
            text = args.text if args.text is not None else sys.stdin.read().strip()
            if not text:
                raise NotificationError("Provide text as an argument or standard input.")
            response = send(text, args.title, args.channel, args.source, args.timeout)
            print(json.dumps(response, ensure_ascii=False, indent=2) if args.json else "Notification sent.")
        return 0
    except NotificationError as exc:
        print(f"{COMMAND_NAME}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"\n{COMMAND_NAME}: aborted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
