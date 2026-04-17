from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from lxml import etree

from .utils import NS_SOAP11, NS_WSDL, qname_to_clark


@dataclass(slots=True)
class WsdlOperation:
    name: str
    endpoint: str
    soap_action: str
    input_message: str | None
    output_message: str | None
    input_element: str | None
    output_element: str | None
    binding_name: str | None = None
    port_type_name: str | None = None


@dataclass(slots=True)
class WsdlModel:
    path: Path
    target_namespace: str | None
    endpoint: str
    operations: list[WsdlOperation]
    namespaces: dict[str | None, str]


def _first(root: etree._Element, xpath: str) -> etree._Element | None:
    matches = root.xpath(xpath, namespaces={"wsdl": NS_WSDL, "soap": NS_SOAP11})
    if matches:
        return matches[0]
    return None


def parse_wsdl(path: Path) -> WsdlModel:
    tree = etree.parse(str(path))
    root = tree.getroot()
    nsmap = dict(root.nsmap)
    target_ns = root.get("targetNamespace")

    messages: dict[str, tuple[str | None, str | None]] = {}
    for message in root.xpath("./wsdl:message", namespaces={"wsdl": NS_WSDL}):
        name = message.get("name")
        part = message.find(f"{{{NS_WSDL}}}part")
        if not name:
            continue
        element = part.get("element") if part is not None else None
        type_attr = part.get("type") if part is not None else None
        messages[name] = (
            qname_to_clark(element, nsmap, fallback_ns=target_ns) if element else None,
            qname_to_clark(type_attr, nsmap, fallback_ns=target_ns) if type_attr else None,
        )

    port_types: dict[str, dict[str, tuple[str | None, str | None]]] = {}
    for port_type in root.xpath("./wsdl:portType", namespaces={"wsdl": NS_WSDL}):
        pt_name = port_type.get("name")
        if not pt_name:
            continue
        op_map: dict[str, tuple[str | None, str | None]] = {}
        for op in port_type.xpath("./wsdl:operation", namespaces={"wsdl": NS_WSDL}):
            op_name = op.get("name")
            if not op_name:
                continue
            input_el = op.find(f"{{{NS_WSDL}}}input")
            output_el = op.find(f"{{{NS_WSDL}}}output")
            input_msg = None
            output_msg = None
            if input_el is not None and input_el.get("message"):
                input_msg = qname_to_clark(input_el.get("message"), nsmap, fallback_ns=target_ns)
            if output_el is not None and output_el.get("message"):
                output_msg = qname_to_clark(output_el.get("message"), nsmap, fallback_ns=target_ns)
            op_map[op_name] = (input_msg, output_msg)
        port_types[pt_name] = op_map

    bindings: dict[str, tuple[str | None, dict[str, str]]] = {}
    for binding in root.xpath("./wsdl:binding", namespaces={"wsdl": NS_WSDL}):
        binding_name = binding.get("name")
        if not binding_name:
            continue
        type_attr = binding.get("type")
        port_type_name = None
        if type_attr:
            clark = qname_to_clark(type_attr, nsmap, fallback_ns=target_ns)
            port_type_name = clark.split("}", 1)[-1] if clark.startswith("{") else clark.split(":")[-1]
        actions: dict[str, str] = {}
        for op in binding.xpath("./wsdl:operation", namespaces={"wsdl": NS_WSDL}):
            op_name = op.get("name")
            soap_op = _first(op, "./soap:operation")
            if op_name:
                actions[op_name] = soap_op.get("soapAction", "") if soap_op is not None else ""
        bindings[binding_name] = (port_type_name, actions)

    endpoint = ""
    binding_for_service: str | None = None
    for service in root.xpath("./wsdl:service", namespaces={"wsdl": NS_WSDL}):
        for port in service.xpath("./wsdl:port", namespaces={"wsdl": NS_WSDL}):
            binding_attr = port.get("binding")
            if binding_attr:
                clark = qname_to_clark(binding_attr, nsmap, fallback_ns=target_ns)
                binding_for_service = clark.split("}", 1)[-1] if clark.startswith("{") else clark.split(":")[-1]
            address = _first(port, "./soap:address")
            if address is not None and address.get("location"):
                endpoint = address.get("location")
                break
        if endpoint:
            break

    operations: list[WsdlOperation] = []
    if binding_for_service and binding_for_service in bindings:
        port_type_name, actions = bindings[binding_for_service]
        op_map = port_types.get(port_type_name or "", {})
        for op_name, action in actions.items():
            input_msg_ref, output_msg_ref = op_map.get(op_name, (None, None))
            input_message_name = (
                input_msg_ref.split("}", 1)[-1] if input_msg_ref and input_msg_ref.startswith("{")
                else input_msg_ref.split(":")[-1] if input_msg_ref else None
            )
            output_message_name = (
                output_msg_ref.split("}", 1)[-1] if output_msg_ref and output_msg_ref.startswith("{")
                else output_msg_ref.split(":")[-1] if output_msg_ref else None
            )
            input_element = messages.get(input_message_name or "", (None, None))[0]
            output_element = messages.get(output_message_name or "", (None, None))[0]
            operations.append(
                WsdlOperation(
                    name=op_name,
                    endpoint=endpoint,
                    soap_action=action,
                    input_message=input_message_name,
                    output_message=output_message_name,
                    input_element=input_element,
                    output_element=output_element,
                    binding_name=binding_for_service,
                    port_type_name=port_type_name,
                )
            )

    return WsdlModel(
        path=path.resolve(),
        target_namespace=target_ns,
        endpoint=endpoint,
        operations=operations,
        namespaces=nsmap,
    )
