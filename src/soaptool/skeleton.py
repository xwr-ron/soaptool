from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from lxml import etree

from .utils import NS_SOAPENV, NS_XSD, localname, qname_to_clark
from .xsd_index import XsdIndex


@dataclass(slots=True)
class BuildContext:
    mode: str = "minimal"
    max_depth: int = 5
    type_stack: list[str] | None = None

    def push(self, qname: str) -> bool:
        if self.type_stack is None:
            self.type_stack = []
        count = self.type_stack.count(qname)
        if count >= 2:
            return False
        self.type_stack.append(qname)
        return True

    def pop(self) -> None:
        if self.type_stack:
            self.type_stack.pop()


XSD_BUILTIN_SAMPLES: dict[str, str] = {
    "string": "string",
    "token": "token",
    "normalizedString": "string",
    "boolean": "true",
    "decimal": "0",
    "integer": "0",
    "int": "0",
    "long": "0",
    "short": "0",
    "byte": "0",
    "double": "0",
    "float": "0",
    "date": "2026-01-01",
    "dateTime": "2026-01-01T00:00:00Z",
    "time": "00:00:00",
    "duration": "P1D",
}


def build_body_element(index: XsdIndex, element_qname: str, mode: str = "minimal") -> etree._Element:
    ctx = BuildContext(mode=mode)
    element_decl = index.find_element(element_qname)
    if element_decl is None:
        raise ValueError(f"Element not found: {element_qname}")
    return _build_element_from_decl(index, element_decl, ctx, forced_qname=element_qname, depth=0)


def _qualify(ns: str | None, local: str) -> str:
    return f"{{{ns}}}{local}" if ns else local


def _build_element_from_decl(
    index: XsdIndex,
    decl: etree._Element,
    ctx: BuildContext,
    forced_qname: str | None = None,
    depth: int = 0,
) -> etree._Element:
    if depth > ctx.max_depth:
        return etree.Element("MaxDepthReached")

    name = decl.get("name")
    ref = decl.get("ref")
    decl_root = decl.getroottree().getroot()
    target_ns = decl_root.get("targetNamespace") if decl_root is not None else None
    qname = forced_qname

    if ref:
        qname = qname_to_clark(ref, decl.nsmap, fallback_ns=target_ns)
        ref_decl = index.find_element(qname)
        if ref_decl is None:
            return etree.Element(ref.split(":")[-1])
        return _build_element_from_decl(index, ref_decl, ctx, forced_qname=qname, depth=depth)

    if not qname:
        qname = _qualify(target_ns, name or "Element")

    if qname.startswith("{"):
        ns, local = qname[1:].split("}", 1)
        elem = etree.Element(etree.QName(ns, local), nsmap={None: ns})
    else:
        elem = etree.Element(qname)

    inline_complex = next((child for child in decl if localname(child.tag) == "complexType"), None)
    inline_simple = next((child for child in decl if localname(child.tag) == "simpleType"), None)
    type_attr = decl.get("type")

    if inline_complex is not None:
        _apply_complex_type(index, elem, inline_complex, ctx, depth + 1)
        return elem

    if inline_simple is not None:
        elem.text = _sample_for_simple_type(inline_simple)
        return elem

    if type_attr:
        type_qname = qname_to_clark(type_attr, decl.nsmap, fallback_ns=target_ns)
        if type_qname.startswith(f"{{{NS_XSD}}}"):
            elem.text = XSD_BUILTIN_SAMPLES.get(type_qname.split("}", 1)[-1], "string")
            return elem
        type_decl = index.find_type(type_qname)
        if type_decl is None:
            elem.text = type_qname.split("}", 1)[-1] if type_qname.startswith("{") else type_qname
            return elem
        if not ctx.push(type_qname):
            return elem
        try:
            if localname(type_decl.tag) == "simpleType":
                elem.text = _sample_for_simple_type(type_decl)
            else:
                _apply_complex_type(index, elem, type_decl, ctx, depth + 1)
        finally:
            ctx.pop()
        return elem

    elem.text = ""
    return elem


def _should_include(element_decl: etree._Element, ctx: BuildContext) -> bool:
    min_occurs = element_decl.get("minOccurs")
    if ctx.mode == "full":
        return True
    if min_occurs is None:
        return True
    return min_occurs != "0"


def _apply_complex_type(index: XsdIndex, target: etree._Element, type_decl: etree._Element, ctx: BuildContext, depth: int) -> None:
    for child in type_decl:
        tag = localname(child.tag)
        if tag in {"sequence", "all"}:
            _apply_compositor(index, target, child, ctx, depth)
        elif tag == "choice":
            _apply_choice(index, target, child, ctx, depth)
        elif tag == "complexContent":
            _apply_complex_content(index, target, child, ctx, depth)
        elif tag == "simpleContent":
            _apply_simple_content(target, child)
        elif tag == "attribute":
            _apply_attribute(target, child)
        elif tag == "attributeGroup":
            _apply_attribute_group(index, target, child, ctx)
        elif tag == "group":
            _apply_group(index, target, child, ctx, depth)


def _apply_complex_content(index: XsdIndex, target: etree._Element, node: etree._Element, ctx: BuildContext, depth: int) -> None:
    for child in node:
        tag = localname(child.tag)
        if tag in {"extension", "restriction"}:
            base = child.get("base")
            if base:
                base_qname = qname_to_clark(base, child.nsmap, fallback_ns=node.getroottree().getroot().get("targetNamespace"))
                base_type = index.find_type(base_qname)
                if base_type is not None and ctx.push(base_qname):
                    try:
                        if localname(base_type.tag) == "complexType":
                            _apply_complex_type(index, target, base_type, ctx, depth + 1)
                    finally:
                        ctx.pop()
            for ext_child in child:
                ext_tag = localname(ext_child.tag)
                if ext_tag in {"sequence", "all"}:
                    _apply_compositor(index, target, ext_child, ctx, depth + 1)
                elif ext_tag == "choice":
                    _apply_choice(index, target, ext_child, ctx, depth + 1)
                elif ext_tag == "attribute":
                    _apply_attribute(target, ext_child)
                elif ext_tag == "attributeGroup":
                    _apply_attribute_group(index, target, ext_child, ctx)
                elif ext_tag == "group":
                    _apply_group(index, target, ext_child, ctx, depth + 1)


def _apply_simple_content(target: etree._Element, node: etree._Element) -> None:
    for child in node:
        tag = localname(child.tag)
        if tag in {"extension", "restriction"}:
            base = child.get("base", "")
            local = base.split(":")[-1].split("}")[-1]
            target.text = XSD_BUILTIN_SAMPLES.get(local, "string")
            for ext_child in child:
                if localname(ext_child.tag) == "attribute":
                    _apply_attribute(target, ext_child)


def _apply_compositor(index: XsdIndex, target: etree._Element, node: etree._Element, ctx: BuildContext, depth: int) -> None:
    for child in node:
        tag = localname(child.tag)
        if tag == "element":
            if not _should_include(child, ctx):
                continue
            target.append(_build_element_from_decl(index, child, ctx, depth=depth))
        elif tag in {"sequence", "all"}:
            _apply_compositor(index, target, child, ctx, depth + 1)
        elif tag == "choice":
            _apply_choice(index, target, child, ctx, depth + 1)
        elif tag == "group":
            _apply_group(index, target, child, ctx, depth + 1)
        elif tag == "any":
            target.append(etree.Element("Any"))


def _apply_choice(index: XsdIndex, target: etree._Element, node: etree._Element, ctx: BuildContext, depth: int) -> None:
    options = [child for child in node if localname(child.tag) in {"element", "sequence", "group"}]
    if not options:
        return
    if ctx.mode == "full":
        selected = options
    else:
        selected = [options[0]]

    for child in selected:
        tag = localname(child.tag)
        if tag == "element":
            target.append(_build_element_from_decl(index, child, ctx, depth=depth))
        elif tag == "sequence":
            _apply_compositor(index, target, child, ctx, depth + 1)
        elif tag == "group":
            _apply_group(index, target, child, ctx, depth + 1)


def _apply_group(index: XsdIndex, target: etree._Element, node: etree._Element, ctx: BuildContext, depth: int) -> None:
    ref = node.get("ref")
    if ref:
        ref_qname = qname_to_clark(ref, node.nsmap, fallback_ns=node.getroottree().getroot().get("targetNamespace"))
        group_decl = index.find_group(ref_qname)
        if group_decl is None:
            return
        for child in group_decl:
            tag = localname(child.tag)
            if tag in {"sequence", "all"}:
                _apply_compositor(index, target, child, ctx, depth + 1)
            elif tag == "choice":
                _apply_choice(index, target, child, ctx, depth + 1)
        return

    for child in node:
        tag = localname(child.tag)
        if tag in {"sequence", "all"}:
            _apply_compositor(index, target, child, ctx, depth + 1)
        elif tag == "choice":
            _apply_choice(index, target, child, ctx, depth + 1)


def _apply_attribute_group(index: XsdIndex, target: etree._Element, node: etree._Element, ctx: BuildContext) -> None:
    ref = node.get("ref")
    if ref:
        ref_qname = qname_to_clark(ref, node.nsmap, fallback_ns=node.getroottree().getroot().get("targetNamespace"))
        group_decl = index.find_attribute_group(ref_qname)
        if group_decl is None:
            return
        for child in group_decl:
            if localname(child.tag) == "attribute":
                _apply_attribute(target, child)


def _apply_attribute(target: etree._Element, attr_decl: etree._Element) -> None:
    name = attr_decl.get("name")
    ref = attr_decl.get("ref")
    if ref:
        name = ref.split(":")[-1].split("}")[-1]
    if not name:
        return
    type_attr = attr_decl.get("type", "string")
    local = type_attr.split(":")[-1].split("}")[-1]
    target.set(name, XSD_BUILTIN_SAMPLES.get(local, "string"))


def _sample_for_simple_type(simple_type: etree._Element) -> str:
    restriction = next((child for child in simple_type if localname(child.tag) == "restriction"), None)
    if restriction is not None:
        enumeration = next((child for child in restriction if localname(child.tag) == "enumeration"), None)
        if enumeration is not None and enumeration.get("value"):
            return enumeration.get("value")
        base = restriction.get("base", "")
        local = base.split(":")[-1].split("}")[-1]
        return XSD_BUILTIN_SAMPLES.get(local, "string")
    return "string"


def build_envelope_xml(body_elem: etree._Element) -> str:
    ns_uri = etree.QName(body_elem).namespace
    nsmap: dict[str | None, str] = {"soapenv": NS_SOAPENV}
    if ns_uri:
        nsmap["ns"] = ns_uri

    env = etree.Element(etree.QName(NS_SOAPENV, "Envelope"), nsmap=nsmap)
    etree.SubElement(env, etree.QName(NS_SOAPENV, "Header"))
    body = etree.SubElement(env, etree.QName(NS_SOAPENV, "Body"))
    body.append(deepcopy(body_elem))
    return etree.tostring(env, encoding="utf-8", pretty_print=True, xml_declaration=False).decode("utf-8")
