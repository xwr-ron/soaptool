from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ..skeleton import build_body_element, build_envelope_xml
from ..wsdl_parser import WsdlModel
from ..xsd_index import XsdIndex


def build_collection(
    wsdl: WsdlModel,
    index: XsdIndex,
    mode: str = "minimal",
    name: str | None = None,
) -> dict:
    collection_name = name or f"{wsdl.path.stem} SOAP"
    items: list[dict] = []

    for op in wsdl.operations:
        raw = ""
        if op.input_element:
            try:
                body_root = build_body_element(index, op.input_element, mode=mode)
                raw = build_envelope_xml(body_root)
            except Exception as exc:  # noqa: BLE001
                raw = (
                    "<error>"
                    f"Failed to build body for {op.name}: {exc}"
                    "</error>"
                )

        items.append(
            {
                "name": op.name,
                "request": {
                    "method": "POST",
                    "header": [
                        {"key": "Content-Type", "value": "text/xml; charset=utf-8", "type": "text"},
                        {"key": "SOAPAction", "value": op.soap_action, "type": "text"},
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": raw,
                        "options": {"raw": {"language": "xml"}},
                    },
                    "url": {
                        "raw": op.endpoint,
                        "host": [op.endpoint],
                    },
                    "description": (
                        f"Input element: {op.input_element or 'unknown'}\n"
                        f"Output element: {op.output_element or 'unknown'}"
                    ),
                },
                "response": [],
            }
        )

    return {
        "info": {
            "name": collection_name,
            "_postman_id": f"soaptool-{datetime.now(timezone.utc).timestamp()}",
            "description": f"Generated from {wsdl.path.name}",
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": items,
        "variable": [
            {"key": "baseUrl", "value": wsdl.endpoint},
        ],
    }


def write_collection(path: Path, collection: dict) -> None:
    path.write_text(json.dumps(collection, indent=2, ensure_ascii=False), encoding="utf-8")
