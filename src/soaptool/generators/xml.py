from __future__ import annotations

from pathlib import Path

from ..skeleton import build_body_element, build_envelope_xml
from ..wsdl_parser import WsdlModel
from ..xsd_index import XsdIndex


def operation_xml(wsdl: WsdlModel, index: XsdIndex, operation_name: str, mode: str = "minimal") -> str:
    for op in wsdl.operations:
        if op.name == operation_name:
            if not op.input_element:
                raise ValueError(f"Operation {operation_name!r} has no input element.")
            root = build_body_element(index, op.input_element, mode=mode)
            return build_envelope_xml(root)
    raise ValueError(f"Operation not found: {operation_name}")


def element_xml(index: XsdIndex, element_qname: str, mode: str = "minimal") -> str:
    root = build_body_element(index, element_qname, mode=mode)
    return build_envelope_xml(root)


def write_xml(path: Path, xml_text: str) -> None:
    path.write_text(xml_text, encoding="utf-8")
