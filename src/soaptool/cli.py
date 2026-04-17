from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .bundle import SessionConfig, bundle_contract
from .generators.postman import build_collection, write_collection
from .generators.xml import operation_xml, element_xml, write_xml
from .wsdl_parser import parse_wsdl
from .xsd_index import XsdIndex


def cmd_bundle(args: argparse.Namespace) -> int:
    manifest = bundle_contract(
        url=args.url,
        out_dir=Path(args.out),
        config=SessionConfig(
            user=args.user,
            password=args.password,
            bearer=args.bearer,
            headers=args.header,
            cert=args.cert,
            key=args.key,
            timeout=args.timeout,
            verify_tls=not args.insecure,
        ),
    )
    print(f"Root saved to: {manifest.root_path}")
    print(f"Manifest: {Path(args.out).expanduser().resolve() / 'manifest.json'}")
    print(f"Downloaded: {len(manifest.nodes)}")
    if manifest.failures:
        print(f"Failures: {len(manifest.failures)}")
        for url, error in manifest.failures.items():
            print(f"  - {url}: {error}")
        return 1
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    wsdl = parse_wsdl(Path(args.wsdl))
    print(f"Endpoint: {wsdl.endpoint or '<not found>'}")
    print(f"{'Operation':24} {'SOAPAction':40} Input")
    print("-" * 100)
    for op in wsdl.operations:
        print(f"{op.name:24} {op.soap_action[:40]:40} {op.input_element or '<none>'}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    wsdl = parse_wsdl(Path(args.wsdl))
    index = XsdIndex.from_wsdl(Path(args.wsdl))

    exit_code = 0
    print(f"WSDL: {wsdl.path}")
    print(f"Endpoint: {wsdl.endpoint or '<not found>'}")
    print(f"Operations: {len(wsdl.operations)}")
    print(f"Elements indexed: {len(index.elements)}")
    print(f"Types indexed: {len(index.types)}")

    for op in wsdl.operations:
        status = "OK"
        details = ""
        if not op.input_element:
            status = "WARN"
            details = "No input element"
        elif index.find_element(op.input_element) is None:
            status = "ERROR"
            details = f"Input element not resolved: {op.input_element}"
            exit_code = 1
        print(f"[{status}] {op.name} {details}".rstrip())
    return exit_code


def cmd_generate_postman(args: argparse.Namespace) -> int:
    wsdl_path = Path(args.wsdl)
    wsdl = parse_wsdl(wsdl_path)
    index = XsdIndex.from_wsdl(wsdl_path)
    collection = build_collection(wsdl, index, mode=args.mode, name=args.name)
    out_path = Path(args.out).expanduser().resolve()
    write_collection(out_path, collection)
    print(f"Collection written to: {out_path}")
    return 0


def cmd_generate_xml(args: argparse.Namespace) -> int:
    wsdl_path = Path(args.wsdl)
    wsdl = parse_wsdl(wsdl_path)
    index = XsdIndex.from_wsdl(wsdl_path)

    if args.operation:
        xml_text = operation_xml(wsdl, index, args.operation, mode=args.mode)
    elif args.element:
        xml_text = element_xml(index, args.element, mode=args.mode)
    else:
        raise ValueError("Either --operation or --element is required.")

    out_path = Path(args.out).expanduser().resolve()
    write_xml(out_path, xml_text)
    print(f"XML written to: {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="soaptool", description="WSDL/XSD bundle and generation toolkit.")
    sub = parser.add_subparsers(dest="command", required=True)

    bundle = sub.add_parser("bundle", help="Download WSDL/XSD bundle without mutating the original files.")
    bundle.add_argument("--url", required=True, help="Root WSDL URL.")
    bundle.add_argument("--out", required=True, help="Output directory.")
    bundle.add_argument("--user")
    bundle.add_argument("--password")
    bundle.add_argument("--bearer")
    bundle.add_argument("--header", action="append", help="Extra header. Example: -H 'Cookie: JSESSIONID=abc'")
    bundle.add_argument("--cert")
    bundle.add_argument("--key")
    bundle.add_argument("--timeout", type=int, default=30)
    bundle.add_argument("--insecure", action="store_true", help="Disable TLS verification.")
    bundle.set_defaults(func=cmd_bundle)

    inspect = sub.add_parser("inspect", help="Inspect a WSDL and print operations.")
    inspect.add_argument("--wsdl", required=True)
    inspect.set_defaults(func=cmd_inspect)

    validate = sub.add_parser("validate", help="Validate operation input element resolution.")
    validate.add_argument("--wsdl", required=True)
    validate.set_defaults(func=cmd_validate)

    generate = sub.add_parser("generate", help="Generate artifacts from a WSDL.")
    gen_sub = generate.add_subparsers(dest="generator", required=True)

    postman = gen_sub.add_parser("postman", help="Generate a Postman collection.")
    postman.add_argument("--wsdl", required=True)
    postman.add_argument("--out", required=True)
    postman.add_argument("--mode", choices=["minimal", "full"], default="minimal")
    postman.add_argument("--name", help="Collection name.")
    postman.set_defaults(func=cmd_generate_postman)

    xml = gen_sub.add_parser("xml", help="Generate XML for one operation or element.")
    xml.add_argument("--wsdl", required=True)
    xml.add_argument("--out", required=True)
    xml.add_argument("--operation")
    xml.add_argument("--element")
    xml.add_argument("--mode", choices=["minimal", "full"], default="minimal")
    xml.set_defaults(func=cmd_generate_xml)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001
        print(f"[soaptool] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
