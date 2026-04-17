from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
import json


@dataclass(slots=True)
class BundleNode:
    url: str
    local_path: str
    referrer: str | None = None
    content_type: str | None = None
    sha256: str | None = None
    discovered_by: str | None = None


@dataclass(slots=True)
class BundleManifest:
    root_url: str
    root_path: str
    nodes: list[BundleNode] = field(default_factory=list)
    failures: dict[str, str] = field(default_factory=dict)

    def add_node(self, node: BundleNode) -> None:
        self.nodes.append(node)

    def to_dict(self) -> dict:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def read(cls, path: Path) -> "BundleManifest":
        payload = json.loads(path.read_text(encoding="utf-8"))
        nodes = [BundleNode(**node) for node in payload.get("nodes", [])]
        return cls(
            root_url=payload["root_url"],
            root_path=payload["root_path"],
            nodes=nodes,
            failures=payload.get("failures", {}),
        )
