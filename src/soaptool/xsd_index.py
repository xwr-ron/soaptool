from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from lxml import etree

from .utils import NS_XSD, localname, qname_to_clark


@dataclass(slots=True)
class SchemaArtifact:
    path: Path
    tree: etree._ElementTree
    target_namespace: str | None
    nsmap: dict[str | None, str]


class XsdIndex:
    def __init__(self) -> None:
        self.schemas: list[SchemaArtifact] = []
        self.elements: dict[str, etree._Element] = {}
        self.types: dict[str, etree._Element] = {}
        self.groups: dict[str, etree._Element] = {}
        self.attribute_groups: dict[str, etree._Element] = {}

    @classmethod
    def from_wsdl(cls, wsdl_path: Path) -> "XsdIndex":
        index = cls()
        wsdl_tree = etree.parse(str(wsdl_path))
        wsdl_root = wsdl_tree.getroot()

        # Inline schemas in wsdl:types
        for schema in wsdl_root.xpath(
            ".//*[local-name()='types']/*[local-name()='schema']"
        ):
            target_ns = schema.get("targetNamespace")
            artifact = SchemaArtifact(
                path=wsdl_path,
                tree=etree.ElementTree(schema),
                target_namespace=target_ns,
                nsmap=dict(schema.nsmap),
            )
            index._register_schema(artifact)

        # Nearby xsd files
        for xsd_path in sorted(wsdl_path.parent.rglob("*.xsd")):
            tree = etree.parse(str(xsd_path))
            root = tree.getroot()
            target_ns = root.get("targetNamespace")
            artifact = SchemaArtifact(
                path=xsd_path,
                tree=tree,
                target_namespace=target_ns,
                nsmap=dict(root.nsmap),
            )
            index._register_schema(artifact)

        return index

    def _register_schema(self, artifact: SchemaArtifact) -> None:
        self.schemas.append(artifact)
        root = artifact.tree.getroot()
        fallback_ns = artifact.target_namespace

        for elem in root.iter():
            tag = localname(elem.tag)
            name = elem.get("name")
            if not name:
                continue
            qname = qname_to_clark(name, {None: fallback_ns} if fallback_ns else {}, fallback_ns=fallback_ns)
            if tag == "element":
                self.elements.setdefault(qname, elem)
            elif tag in {"complexType", "simpleType"}:
                self.types.setdefault(qname, elem)
            elif tag == "group":
                self.groups.setdefault(qname, elem)
            elif tag == "attributeGroup":
                self.attribute_groups.setdefault(qname, elem)

    def find_element(self, qname: str | None) -> etree._Element | None:
        if not qname:
            return None
        if qname in self.elements:
            return self.elements[qname]
        return self._find_by_localname(self.elements, qname)

    def find_type(self, qname: str | None) -> etree._Element | None:
        if not qname:
            return None
        if qname in self.types:
            return self.types[qname]
        return self._find_by_localname(self.types, qname)

    def find_group(self, qname: str | None) -> etree._Element | None:
        if not qname:
            return None
        if qname in self.groups:
            return self.groups[qname]
        return self._find_by_localname(self.groups, qname)

    def find_attribute_group(self, qname: str | None) -> etree._Element | None:
        if not qname:
            return None
        if qname in self.attribute_groups:
            return self.attribute_groups[qname]
        return self._find_by_localname(self.attribute_groups, qname)

    @staticmethod
    def _find_by_localname(mapping: dict[str, etree._Element], qname: str) -> etree._Element | None:
        if qname.startswith("{"):
            local = qname.split("}", 1)[-1]
        else:
            local = qname.split(":")[-1]
        matches = [value for key, value in mapping.items() if key.split("}", 1)[-1] == local]
        if len(matches) == 1:
            return matches[0]
        return None
