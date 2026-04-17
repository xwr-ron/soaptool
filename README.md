# Soap Tool

A pragmatic CLI for downloading, inspecting, validating, and generating artifacts from SOAP/WSDL/XSD bundles **without mutating the original contract files**.

## Table of Contents

* [Why this repository was created](#why-this-repository-was-created)
* [What problem it solves](#what-problem-it-solves)
* [Installation](#installation)
* [Commands](#commands)
* [Typical workflow](#typical-workflow)
* [Current scope](#current-scope)

## Why this repository was created

This repository was created after a practical integration problem with a real SOAP service.

The original goal was simple: take a WSDL with external XSD schemas, import it into Postman, and get usable request bodies automatically. In practice, that flow turned out to be unreliable for more complex enterprise contracts:

* Postman could fail to resolve external schemas correctly.
* Generated request bodies could be empty or contain placeholder errors instead of valid XML.
* Naive scripts that downloaded and rewrote WSDL/XSD files could accidentally break namespace declarations and QName references.
* Once the original contract was mutated, downstream tools could no longer resolve elements and types correctly.

This repository exists to solve that class of problems in a safer and more reusable way.

Instead of relying on fragile import behavior or rewriting the original SOAP contract, `soaptool` keeps the original files intact, builds an internal model of the contract, and generates artifacts such as Postman collections or XML skeletons from that model.

## What problem it solves

`soaptool` is meant for situations where you have one or more of the following:

* a WSDL that imports multiple XSD files
* remote schemas behind authentication
* enterprise SOAP contracts with a lot of indirection
* tools that do not correctly resolve namespaces, imports, groups, or referenced elements
* a need to generate request templates without manually crafting SOAP envelopes

1. **Never mutate originals.**
   Downloaded files are stored as reference inputs.

2. **Separate concerns.**
   Downloading, resolving, validating, and generating are different stages.

3. **Work from a contract model.**
   Artifacts should be generated from a resolved representation of the service, not from ad-hoc string hacks.

4. **Prefer pragmatic coverage.**
   The target is real-world enterprise WSDL/XSD usage, not theoretical completeness.

## Installation

```bash
pip install -e .
```

For development:

```bash
pip install -e .[dev]
```

## Commands

### bundle

Downloads a WSDL and all referenced schemas into a local bundle **without rewriting the originals**.

```bash
soaptool bundle --url "https://host/service?wsdl" --out ./soap_bundle
```

Examples with auth:

```bash
soaptool bundle --url "https://host/service?wsdl" --out ./soap_bundle \
  --user USER --password PASS
```

```bash
soaptool bundle --url "https://host/service?wsdl" --out ./soap_bundle \
  --bearer TOKEN
```

## inspect

Shows discovered endpoint, operations, SOAP actions, and related input elements.

```bash
soaptool inspect --wsdl ./soap_bundle/original/service.wsdl
```

## validate

Checks whether operations and referenced input elements can be resolved.

```bash
soaptool validate --wsdl ./soap_bundle/original/service.wsdl
```

## generate postman

Builds a Postman collection from the resolved service model.

```bash
soaptool generate postman \
  --wsdl ./soap_bundle/original/service.wsdl \
  --out ./service.postman_collection.json
```

## generate xml

Builds a SOAP XML skeleton for a given operation or element.

```bash
soaptool generate xml \
  --wsdl ./soap_bundle/original/service.wsdl \
  --operation searchFlightsFlex \
  --out ./searchFlightsFlex.xml
```

## Typical workflow

```bash
soaptool bundle --url "https://host/service?wsdl" --out ./soap_bundle
soaptool inspect --wsdl ./soap_bundle/original/service.wsdl
soaptool validate --wsdl ./soap_bundle/original/service.wsdl
soaptool generate postman --wsdl ./soap_bundle/original/service.wsdl --out ./service.postman_collection.json
soaptool generate xml --wsdl ./soap_bundle/original/service.wsdl --operation SomeOperation --out ./SomeOperation.xml
```

## Current scope

The project is intended to support practical WSDL 1.1 and common XSD usage patterns, including:

* `wsdl:import`
* `xsd:import`
* `xsd:include`
* `xsd:redefine`
* `complexType`
* `simpleType`
* `sequence`
* `choice`
* `all`
* `group`
* `attributeGroup`
* common extension patterns
