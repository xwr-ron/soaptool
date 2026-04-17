from pathlib import Path
import json

from soaptool.wsdl_parser import parse_wsdl
from soaptool.xsd_index import XsdIndex
from soaptool.skeleton import build_body_element, build_envelope_xml
from soaptool.generators.postman import build_collection


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "simple"


def test_parse_wsdl_and_generate_body():
    wsdl_path = FIXTURE_DIR / "simple.wsdl"
    wsdl = parse_wsdl(wsdl_path)
    assert wsdl.endpoint == "https://example.com/soap"
    assert wsdl.operations[0].name == "SearchFlights"

    index = XsdIndex.from_wsdl(wsdl_path)
    root = build_body_element(index, wsdl.operations[0].input_element, mode="full")
    xml_text = build_envelope_xml(root)

    assert "SearchFlightsRQ" in xml_text
    assert "PointOfSale" in xml_text
    assert "Agent" in xml_text
    assert "Email" in xml_text
    assert 'version="string"' in xml_text
    assert "Party" in xml_text


def test_generate_postman_collection():
    wsdl_path = FIXTURE_DIR / "simple.wsdl"
    wsdl = parse_wsdl(wsdl_path)
    index = XsdIndex.from_wsdl(wsdl_path)
    collection = build_collection(wsdl, index, mode="full", name="Test SOAP")
    payload = json.dumps(collection)

    assert collection["info"]["name"] == "Test SOAP"
    assert "SearchFlights" in payload
    assert "http://example.com/SearchFlights" in payload
    assert "https://example.com/soap" in payload
    assert "SearchFlightsRQ" in payload
