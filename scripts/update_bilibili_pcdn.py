#!/usr/bin/env python3
"""Build narrowly scoped Quantumult X rules without executing upstream code."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ("mbga", "https://raw.githubusercontent.com/SukkaW/Make-Bilibili-Great-Than-Ever-Before/master/src/core/player/cdn-classify.ts"),
    ("pcdn", "https://raw.githubusercontent.com/uselibrary/PCDN/main/pcdn.list"),
)
OUTPUTS = (
    "quantumultx/filter/bilibili-pcdn.list",
    "quantumultx/filter/bilibili-pcdn-extended.list",
    "sources/bilibili-pcdn-lock.json",
)
MAX_BYTES = 1024 * 1024
PROTECTED_ROOTS = {
    "bilibili.com", "biliapi.com", "biliapi.net", "bilivideo.com",
    "bilivideo.cn", "bilivideo.net", "hdslb.com", "akamaized.net",
    "com", "cn", "net",
}
SAFE_HOSTS = (
    "www.bilibili.com", "api.bilibili.com", "passport.bilibili.com",
    "grpc.biliapi.net", "api.biliapi.net", "i0.hdslb.com",
    "upos-sz-mirrorhw.bilivideo.com", "upos-sz-mirrorcos.bilivideo.com",
    "upos-sz-mirrorali.bilivideo.com", "upos-hz-mirrorakam.akamaized.net",
    "cn-hnzz-cm-01-01.bilivideo.com", "api.live.bilibili.com",
)


class UpdateError(ValueError):
    pass


def validate_rule(rule: tuple[str, str]) -> tuple[str, str]:
    kind, host = rule
    if kind not in {"host", "host-suffix", "host-wildcard"}:
        raise UpdateError(f"Unsupported rule type: {kind}")
    if not re.fullmatch(r"[a-z0-9*?](?:[a-z0-9*?.-]*[a-z0-9])?", host):
        raise UpdateError(f"Invalid hostname: {host}")
    if ".." in host or len(host) > 253 or len(host.split(".")) < 2:
        raise UpdateError(f"Invalid hostname: {host}")
    if host in PROTECTED_ROOTS:
        raise UpdateError(f"Broad service-wide blocking is not permitted: {host}")
    if kind != "host-wildcard" and ("*" in host or "?" in host):
        raise UpdateError(f"Wildcard requires host-wildcard: {host}")
    if any("*" in label or "?" in label for label in host.split(".")[-2:]):
        raise UpdateError(f"Wildcard cannot span registrable suffix: {host}")
    for safe in SAFE_HOSTS:
        if matches(rule, safe):
            raise UpdateError(f"Rule would block normal Bilibili traffic: {kind},{host}")
    return rule


def matches(rule: tuple[str, str], host: str) -> bool:
    kind, pattern = rule
    if kind == "host":
        return host == pattern
    if kind == "host-suffix":
        return host == pattern or host.endswith("." + pattern)
    return fnmatch.fnmatchcase(host, pattern)


def parse_mbga(text: str) -> tuple[set, set]:
    block = re.search(
        r"const knownP2pCdnDomainPattern\s*=\s*createRetrieKeywordFilter\(\[(.*?)\]\);",
        text, re.S,
    )
    if not block:
        raise UpdateError("MBGA classifier changed: known P2P array not found")
    body = re.sub(r"//[^\n]*", "", block.group(1))
    literals = re.findall(r"['\"]([^'\"\\]+)['\"]", body)
    residue = re.sub(r"['\"][^'\"\\]+['\"]", "", body)
    if residue.strip(" \t\r\n,") or not 2 <= len(literals) <= 128:
        raise UpdateError("MBGA P2P array is empty, too large, or no longer literal data")
    basic, extended = set(), set()
    for token in literals:
        if token in {"302ppio", "302kodo"}:
            extended.add(("host-wildcard", f"*{token}*.bilivideo.com"))
        elif token == ".mcdn.bilivideo":
            basic.update(("host-suffix", f"mcdn.bilivideo.{tld}") for tld in ("cn", "com", "net"))
        elif "." in token:
            host = token.lstrip(".")
            target = basic if host == "szbdyd.com" or host.startswith("mcdn.bilivideo.") else extended
            kind = "host" if host.endswith((".bilivideo.com", ".bilivideo.cn", ".bilivideo.net")) else "host-suffix"
            target.add((kind, host))
        else:
            raise UpdateError(f"Unrecognized MBGA keyword; review required: {token}")
    if "subdomain.includes('302')" in text or 'subdomain.includes("302")' in text:
        extended.add(("host-wildcard", "*302*.bilivideo.com"))
        extended.discard(("host-wildcard", "*302ppio*.bilivideo.com"))
        extended.discard(("host-wildcard", "*302kodo*.bilivideo.com"))
    if not basic:
        raise UpdateError("MBGA no longer provides any recognizable basic domains")
    return basic, extended


def parse_pcdn(text: str) -> set:
    result = set()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [x.strip() for x in line.split(",")]
        if len(fields) != 2:
            raise UpdateError(f"PCDN source format changed: {line[:100]}")
        kind, host = fields
        # This is a multi-service collection. Import only these reviewed Bilibili patterns.
        if kind == "DOMAIN-SUFFIX" and (host == "szbdyd.com" or re.fullmatch(r"mcdn\.bilivideo\.(?:cn|com|net)", host)):
            result.add(("host-suffix", host))
        elif kind == "DOMAIN-REGEX" and host == ".*pcdn.*biliapi.net":
            # Require the literal dot; don't reproduce the source regex's unescaped dots.
            result.add(("host-wildcard", "*pcdn*.biliapi.net"))
    if not result:
        raise UpdateError("PCDN source has no recognizable Bilibili entries")
    return result


def read_manual(root: Path) -> tuple[set, set]:
    data = json.loads((root / "sources/bilibili-pcdn-manual.json").read_text(encoding="utf-8"))
    return set(map(tuple, data["basic"])), set(map(tuple, data["extended"]))


def fetch_source(url: str) -> str:
    for attempt in range(2):
        try:
            request = Request(url, headers={"User-Agent": "uid21-quantumultx-rules/1.0"})
            with urlopen(request, timeout=25) as response:
                payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise UpdateError(f"Upstream exceeded size limit: {url}")
            return payload.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            if attempt:
                raise UpdateError(f"Cannot read upstream: {url}: {exc}") from exc
            time.sleep(1)
    raise AssertionError("unreachable")


def render(rules: set, extended: bool) -> str:
    description = "Extended media-host blocking (includes the basic list)." if extended else "Basic Bilibili PCDN blocking."
    lines = [
        "# Generated by scripts/update_bilibili_pcdn.py; do not edit this file.",
        f"# {description}",
        "# No MITM needed. Blocking relies on the client choosing another playback URL.",
        "# Sources and licenses: https://github.com/uid21/quantumultx-rules#sources",
        "# Edit sources/bilibili-pcdn-manual.json to keep local additions across updates.",
        "",
    ]
    lines.extend(f"{kind}, {host}, reject" for kind, host in sorted(rules))
    return "\n".join(lines) + "\n"


def build(root: Path, source_text: dict[str, str]) -> dict[str, str]:
    basic, extended = read_manual(root)
    mbga_basic, mbga_extended = parse_mbga(source_text["mbga"])
    basic |= mbga_basic | parse_pcdn(source_text["pcdn"])
    extended |= basic | mbga_extended
    for group in (basic, extended):
        if not 2 <= len(group) <= 128:
            raise UpdateError("Unreasonable generated rule count")
        for rule in group:
            validate_rule(rule)
    lock = {
        "sources": [
            {"id": name, "url": url, "sha256": hashlib.sha256(source_text[name].encode()).hexdigest()}
            for name, url in SOURCES
        ],
        "rules": {"basic": len(basic), "extended": len(extended)},
    }
    return dict(zip(OUTPUTS, [render(basic, False), render(extended, True), json.dumps(lock, ensure_ascii=False, indent=2) + "\n"]))


def update(root: Path = ROOT, source_dir: Path | None = None, check: bool = False) -> list[str]:
    # Download and validate every source before touching any committed output.
    texts = {
        name: (source_dir / f"{name}.txt").read_text(encoding="utf-8") if source_dir else fetch_source(url)
        for name, url in SOURCES
    }
    outputs = build(root, texts)
    changed = []
    for relative, content in outputs.items():
        target = root / relative
        if target.exists() and target.read_text(encoding="utf-8") == content:
            continue
        changed.append(relative)
    if check:
        return changed
    for relative in changed:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(outputs[relative], encoding="utf-8", newline="\n")
        temporary.replace(target)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, help="Read mbga.txt and pcdn.txt locally (offline reproduction)")
    parser.add_argument("--check", action="store_true", help="Return failure if generated files would change")
    args = parser.parse_args()
    try:
        changed = update(source_dir=args.source_dir, check=args.check)
    except (UpdateError, OSError, json.JSONDecodeError) as exc:
        print(f"Update stopped; existing output is preserved: {exc}", file=sys.stderr)
        return 1
    print("Changed: " + ", ".join(changed) if changed else "Rules are current; no changes.")
    return int(args.check and bool(changed))


if __name__ == "__main__":
    raise SystemExit(main())
