from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
import requests
from lxml import etree

from .manifest import BundleManifest, BundleNode
from .utils import (
    normalize_url,
    parse_xml_bytes,
    sha256_bytes,
    url_to_local_path,
    localname,
)


@dataclass(slots=True)
class SessionConfig:
    user: str | None = None
    password: str | None = None
    bearer: str | None = None
    headers: list[str] | None = None
    cert: str | None = None
    key: str | None = None
    timeout: int = 30
    verify_tls: bool = True


def build_session(config: SessionConfig) -> requests.Session:
    session = requests.Session()
    if config.user:
        session.auth = (config.user, config.password or "")
    if config.bearer:
        session.headers["Authorization"] = f"Bearer {config.bearer}"
    for header in config.headers or []:
        if ":" not in header:
            raise ValueError(f"Invalid header value: {header!r}. Use 'Header: Value'")
        key, value = header.split(":", 1)
        session.headers[key.strip()] = value.strip()
    if config.cert and config.key:
        session.cert = (config.cert, config.key)
    elif config.cert:
        session.cert = config.cert
    return session


def discover_references(tree: etree._ElementTree, base_url: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    root = tree.getroot()
    for elem in root.iter():
        tag = localname(elem.tag)
        attrs = elem.attrib
        if tag == "import":
            location = attrs.get("location") or attrs.get("schemaLocation")
            if location:
                refs.append((urljoin(base_url, location), tag))
        elif tag in {"include", "redefine"}:
            schema_location = attrs.get("schemaLocation")
            if schema_location:
                refs.append((urljoin(base_url, schema_location), tag))
    return refs


def bundle_contract(url: str, out_dir: Path, config: SessionConfig) -> BundleManifest:
    session = build_session(config)
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    root_url = normalize_url(url)
    manifest = BundleManifest(root_url=root_url, root_path="")
    seen: set[str] = set()

    def crawl(target_url: str, referrer: str | None = None, discovered_by: str | None = None) -> Path | None:
        normalized = normalize_url(target_url)
        if normalized in seen:
            return None
        seen.add(normalized)

        try:
            response = session.get(normalized, timeout=config.timeout, verify=config.verify_tls)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            manifest.failures[normalized] = str(exc)
            return None

        payload = response.content
        content_type = response.headers.get("Content-Type", "")
        local_path = url_to_local_path(normalized, out_dir, payload, content_type)
        local_path.write_bytes(payload)

        if not manifest.root_path:
            manifest.root_path = str(local_path)

        manifest.add_node(
            BundleNode(
                url=normalized,
                local_path=str(local_path),
                referrer=referrer,
                content_type=content_type,
                sha256=sha256_bytes(payload),
                discovered_by=discovered_by,
            )
        )

        tree = parse_xml_bytes(payload)
        if tree is None:
            return local_path

        for ref_url, ref_kind in discover_references(tree, normalized):
            crawl(ref_url, referrer=normalized, discovered_by=ref_kind)

        return local_path

    crawl(root_url)
    manifest.write(out_dir / "manifest.json")
    return manifest
