# ARXML-to-FLYNC Converter Development Plan

## Purpose

Develop a maintainable AUTOSAR ARXML-to-FLYNC converter suitable for a community merge request. The converter must support a single ARXML file and multi-file ECU extracts while preserving AUTOSAR engineering meaning and using the existing FLYNC SDK and converter framework.

## Current Baseline

The first draft currently supports:

- Single `.arxml` file or directory input.
- ECU fragment merging by `SHORT-NAME`.
- ECU, communication-controller, and Ethernet-channel discovery.
- Validated `FLYNCModel` generation.
- FLYNC workspace output.
- Pluggy registration as the `arxml` converter.
- Synthetic tests and converter-suite coverage.

The draft was validated locally against:

- Audi: 2 files, 19 ECU instances.
- GM: 6 files, 5 ECU instances.

The current implementation is intentionally limited. It maps bounded CAN/LIN, PDU, Ethernet L2/L3, SOME/IP interface metadata, and diagnostic inventory records, but does not claim complete deployment, payload, or cross-file reference semantics.

## Implementation Status After First Phase Pass

Implemented in the current converter:

- Phase 1 foundation: controller-owned normalized IR, source provenance, deterministic ECU fragment merging, and ownership-preserving interface mapping.
- Phase 2 foundation: namespace/schema capture, UUID index, file/directory discovery, repeated-fragment handling, conflict diagnostics, and synthetic reference tests.
- Phase 3 foundation: validated ECU/controller/Ethernet workspace generation without assigning interfaces across unrelated controllers.
- Phase 4 foundation: conservative CAN channel discovery and basic FLYNC CAN bus output when a supported baud rate is explicitly present.
- Phase 5 boundary: SOME/IP and diagnostic elements are detected and reported as structured diagnostics instead of being silently discarded.

Remaining semantic gaps:

- Full AUTOSAR implemented/application datatype chains, data constraints, value tables, invalid values, multiplexing, and signal groups.
- Complete frame-triggering/package-aware reference resolution, extended identifier evidence, and LIN schedules/master/slave semantics.
- Ethernet physical link/switch topology when ECU-port semantics are explicit in the source.
- SOME/IP service-instance/provider/consumer deployments, socket binding, and SOME/IP-SD timing/deployment semantics.
- Diagnostic payload datatype records, DoIP server bindings, UDS sessions, routines, and security-access semantics.

## Resumable Implementation Status

Last checkpoint: 2026-09-30

### Completed

- [x] Phase 1/2 normalized IR: controller ownership, provenance, namespaces, UUID index, deterministic fragment merge, conflict diagnostics.
- [x] Phase 3 ECU/controller/Ethernet structural FLYNC model generation.
- [x] Phase 4 CAN channel discovery and basic supported-rate CAN bus output.
- [x] Phase 5 unsupported SOME/IP/diagnostic detection with non-fatal diagnostics.
- [x] Browser generation of SVG/HTML/PUML plus generated FLYNC workspace ZIP downloads.
- [x] PDU/signal inventory IR: `I-SIGNAL`, `I-SIGNAL-I-PDU`, signal references, lengths, bit positions, and byte-order metadata.
- [x] Synthetic tests for PDU/signal placement extraction.
- [x] Typed signal/PDU/frame emission: explicit AUTOSAR base data types, linear `COMPU-METHOD` coefficients, validated `Signal`/`SignalInstance`/`StandardPDU`, and explicit CAN/LIN frame placement.
- [x] Synthetic end-to-end CAN fixture for datatype, scaling, limits, PDU placement, and frame identifier.
- [x] Normalized `PDU-TO-FRAME-MAPPING` resolution with frame/PDU reference checks, nonzero bit offsets, duplicate/conflict/overlap/incomplete-placement diagnostics, and direct-frame compatibility.
- [x] Explicit CAN-FD frame/bus fields and LIN checksum mapping where represented; synthetic positive and negative coverage added.
- [x] Focused regression after mapping emission: 17 tests passed.
- [x] Normalized Ethernet Layer 2/3 records for controller-owned physical channels, explicit MAC addresses, VLAN interfaces, IPv4/IPv6 endpoints, and UDP/TCP sockets.
- [x] Conservative Ethernet FLYNC emission using existing `EthernetInterfaceConfig`, `VirtualControllerInterface`, `SocketContainer`, `SocketUDP`, and `SocketTCP` models.
- [x] Synthetic Ethernet tests for physical-channel ownership, VLAN/IP endpoints, complete UDP/TCP sockets, incomplete TCP profile omission, and unresolved topology diagnostics.
- [x] Normalized SOME/IP service-interface metadata for explicit service/version IDs, method/event/field IDs, and event-group references; validated emission uses existing FLYNC types and neutral required timing scaffolding.
- [x] Synthetic SOME/IP positive and incomplete-member coverage, including unresolved event-group members and missing identifiers.
- [x] Normalized diagnostic inventory for explicit DoIP logical addresses, UDS service identifiers, DIDs, and DTCs; safe DTC and fixed-length empty DID records emit into validated UDS catalogs.
- [x] Synthetic diagnostic positive and incomplete-DID coverage; DoIP/UDS deployment and unsupported diagnostic payload semantics remain diagnostics.
- [x] Full converter regression after Ethernet/SOME/IP/diagnostic slices: 286 tests passed.
- [x] Topology UML displays VLAN/IP interface notes and directed provider-to-consumer SOME/IP edges when the FLYNC model contains matching deployments.

### In Progress

- [ ] Expand datatype resolution beyond explicit `SW-BASE-TYPE` encodings and support implemented/application datatype chains.
- [ ] Resolve AUTOSAR `DATA-CONSTR`, unit definitions, value tables, invalid values, multiplexing, and signal groups.
- [ ] Add frame-triggering reference resolution beyond direct frame references, extended identifier evidence, and LIN schedules/master-slave semantics.
- [ ] Expand negative synthetic tests for unresolved datatype/COMPU references, unsupported formulas, and malformed frame-triggering structures.
- [ ] Resolve service-instance and diagnostic-server deployment references without fabricating transport or timing values.

### Next Resume Point

The current slice emits `StandardPDU` definitions only when every mapped signal has an explicit base datatype, supported signedness/float encoding, explicit bit placement/byte order, and a resolved linear `COMPU-METHOD`. PDU `LENGTH` is normalized from AUTOSAR bits to FLYNC bytes. CAN frames additionally require explicit bus, payload length, PDU reference, CAN ID, and identifier format; LIN frames require explicit bus, payload length, PDU reference, and LIN ID. Invalid or incomplete records remain warning diagnostics and are not emitted.

The PDU-to-frame gate is now implemented for normalized `PDU-TO-FRAME-MAPPING` records and direct frame references. Mappings are resolved by frame/PDU short-name identity within the merged current IR, require explicit frame/PDU/bit placement, reject duplicate or overlapping ranges before model creation, and emit `PDUInstance` offsets into CAN/LIN frames. CAN-FD requires an explicit bus data rate and uses the FLYNC CAN-FD payload validation; LIN preserves an explicit classic/enhanced checksum value.

The Ethernet L2/L3 slice is now implemented for explicit controller-owned physical channels. It maps only source-backed MAC addresses, VLAN IDs, IPv4 subnet masks, IPv6 prefix lengths, UDP ports, and TCP ports with explicit TCP profiles. Socket records without an explicit or unambiguous address/port, and TCP records without a profile, remain warning diagnostics and are not emitted. Ethernet topology connections are retained for unresolved-reference diagnostics but are not emitted because the current input does not establish FLYNC ECU-port/link semantics.

The bounded SOME/IP/diagnostic slice is now implemented for explicit interface metadata and identifier inventory. SOME/IP services require explicit service ID plus major/minor versions; methods, events, fields, and event groups emit only when their identifiers and event-group member references are complete. Existing FLYNC timing/configuration models receive neutral required scaffolding because ARXML timing/deployment semantics are not mapped yet. DTCs emit from explicit 24-bit identifiers; DIDs emit only when an explicit payload byte length permits a truthful empty `DiagDataRecord`. DoIP logical addresses, UDS service IDs, incomplete DIDs, unsupported payload/datatype encodings, service deployments, sockets, and diagnostic server bindings remain provenance-bearing diagnostics.

Next resume point: implement package-aware SOME/IP service-instance/provider/consumer and socket deployment resolution in the ARXML importer. The diagram renderer can display these flows when deployments exist in a FLYNC model, but the current ARXML importer does not yet create them, so ARXML-derived diagrams do not gain service arrows from interface declarations alone. Then extend diagnostic payload datatype records and DoIP/UDS server bindings. Keep unsupported timing, transport, and OEM-specific payload semantics as provenance-bearing diagnostics until their source mappings are explicit.

## Non-Negotiable Constraints

- Read Audi and GM ARXML only in place and keep the source trees read-only.
- Never commit proprietary ARXML, OEM identifiers, ECU names, signal names, UUIDs, addresses, or derived confidential mappings.
- Use synthetic, minimal, non-confidential ARXML fixtures in committed tests.
- Never transmit ARXML or proprietary derived data to external services.
- Do not run OEM generators, RTE/BSW generators, flashing tools, or live ECU commands.
- Do not claim complete AUTOSAR, OEM, or production support from a limited sample.
- Never hide unsupported or lossy mappings.
- Never commit, push, publish, or submit the MR from the coding agent.

## Phase 1: Correct the Intermediate Representation

Replace the flattened `ARXLEcu` structure with a normalized representation that preserves relationships:

```text
ARXMLDocument
├── ECU instances
│   ├── controllers
│   │   ├── controller identity
│   │   ├── controller type
│   │   └── interfaces
│   ├── physical channels
│   └── source provenance
├── packages
├── references
└── diagnostics
```

Required outcomes:

- Preserve controller-to-interface ownership.
- Preserve source file and XML path for mapped elements.
- Avoid assigning every interface to every controller.
- Detect conflicting definitions across fragments.
- Keep output ordering deterministic.
- Support `DEST` and package-path references instead of short-name-only lookup.

Acceptance checks:

- Synthetic multi-controller fixture with repeated interface names.
- Synthetic repeated ECU fragments that merge without losing ownership.
- Synthetic conflicting fragment that fails with an actionable diagnostic.
- Provenance is available for every normalized ECU, controller, and interface.

## Phase 2: Input and Reference Resolution

Add a dedicated ARXML input layer:

- Discover `.arxml` files from a file, directory, or explicit file set.
- Parse namespaces and AUTOSAR schema/version declarations.
- Build a cross-file index for absolute references, package paths, UUIDs, and short names.
- Resolve references only when unambiguous.
- Report unresolved, duplicate, and conflicting references with file/path context.
- Disable external entity expansion and network access during XML parsing.

Tests:

- One-file input.
- Multi-file references.
- Duplicate UUID.
- Duplicate package path.
- Missing reference.
- Same short name in different packages.
- AUTOSAR namespace/version variation.
- Audi and GM-specific extension elements represented by synthetic equivalents.

## Phase 3: ECU and Network Topology Mapping

Map AUTOSAR concepts into FLYNC only when the source semantics are present:

| AUTOSAR | FLYNC |
|---|---|
| `ECU-INSTANCE` | `ECU` |
| communication controller | `Controller` |
| Ethernet physical channel | `EthernetInterface` / `ECUPort` |
| CAN controller | `CANInterface` |
| LIN controller | LIN interface |
| physical channel connection | internal/system topology |
| ECU metadata | `ECUMetadata` |

Rules:

- Do not invent PHY, speed, role, VLAN, or address values.
- Map only values explicitly present in ARXML.
- Emit an explicit unsupported or unknown diagnostic when FLYNC requires data unavailable in ARXML.
- Keep ECU extract semantics separate from physical network topology.

Acceptance checks:

- Generated workspaces load through `FLYNCWorkspace.load_workspace()`.
- No controller receives unrelated interfaces.
- Multi-controller GM extracts validate without ambiguity.
- Topology is emitted only when its source semantics are available.

## Phase 4: CAN, LIN, Ethernet, and PDU Mapping

Implement communication in this order:

1. CAN clusters, channels, frames, IDs, signals, positions, lengths, byte order, scaling, limits, and CAN-FD attributes.
2. LIN clusters, schedules, frames, signals, and master/slave semantics where represented.
3. Ethernet frames, PDUs, PDU mappings, IP/VLAN data, and socket deployments.
4. Common data types, units, invalid values, limits, multiplexing, and container semantics.

Each stage must map to existing FLYNC model types rather than converter-only output structures.

## Phase 5: SOME/IP and Diagnostics

After signal and PDU foundations are stable, add:

- SOME/IP service interfaces.
- Methods, events, fields, and event groups.
- Service IDs, instance IDs, major/minor versions.
- UDP/TCP deployments.
- DoIP and UDS configuration where represented.
- Diagnostic identifiers and DTC mappings.

Unsupported diagnostic content must produce structured diagnostics instead of being silently ignored.

## Phase 6: Converter API and CLI

The current `ConverterConfig(config_path: str)` contract may be insufficient for explicit multi-file ECU extracts. Before changing it:

- Check existing CLI behavior and all converter implementations.
- Preserve JSON, YAML, DBC, and native FLYNC compatibility.
- Prefer directory semantics when it safely represents an ECU extract.
- Introduce an ARXML-specific configuration model only when explicit file lists, profiles, or reference roots require it.
- Add OEM profiles only when demonstrated differences require them.

Target usage:

```powershell
flync-converter convert `
  --source path\to\arxml-directory `
  --source-format arxml `
  --output path\to\flync-workspace `
  --output-format flync
```

## Phase 7: Diagnostics and Provenance

Define diagnostics for:

- Unsupported AUTOSAR elements.
- Missing required mappings.
- Unresolved references.
- Duplicate definitions.
- Conflicting fragments.
- Lossy conversions.
- Ambiguous short names.
- Schema/version mismatches.

Every diagnostic should include severity, source file, XML path, AUTOSAR element, reason, and suggested action.

Model-level validation errors must follow FLYNC's structured error catalog. Do not introduce bare `ValueError` in FLYNC validators.

## Phase 8: Tests and Fixtures

Commit only synthetic fixtures. Add tests for:

- XML parsing.
- Namespace and version handling.
- Reference resolution.
- OEM-profile mapping behavior using anonymized synthetic structures.
- Converter contract behavior.
- FLYNC model validation.
- Workspace serialization and reload.
- Deterministic output.
- Malformed, unsupported, unresolved, duplicate, and conflicting input.

Required checks:

```powershell
uv run pytest tests/converter_tests -n 0
uv run black --check --diff --line-length 149 src tests
uv run isort --check --diff --line-length 149 src tests
uv run flake8 src scripts
uv run mypy src scripts
uv run python scripts/ci/validate_examples.py
uv run python scripts/ci/check_example_superset.py
```

If the environment cannot run a check because of optional dependencies, platform requirements, or network access, report that precisely.

## Phase 9: Documentation and MR Handoff

Update:

- Converter CLI documentation.
- Converter architecture/design documentation.
- Release notes for user-visible support.
- Mapping coverage and limitation tables.
- Synthetic usage examples.

Before MR handoff, review scope, API compatibility, dependency and license impact, privacy leaks, accidental fixture data, deterministic output, and known limitations. Generated error-catalog documentation must be updated only through `flync errors sync`.

## Immediate Next Iteration

Implement Phase 1 and Phase 2 before adding CAN/LIN/PDU mappings:

1. Replace the flattened `ARXLEcu` structure with controller-owned interfaces.
2. Add source provenance.
3. Add namespace and schema detection.
4. Add a cross-file reference index.
5. Add synthetic multi-file reference tests.
6. Revalidate both local OEM datasets while reporting only abstract counts and diagnostics.

The next iteration is complete only when the normalized representation can distinguish same-named interfaces belonging to different controllers and can explain unresolved or conflicting cross-file references without silently guessing.

## Extension Plan: Ethernet, PDU, SOME/IP, and Diagnostics

The current generated workspace is structurally valid but intentionally sparse. The next work must add communication semantics in dependency order so the generated FLYNC configuration and topology diagram become useful without inventing values.

### Layer A: Shared Reference and Mapping Infrastructure

Before adding more AUTOSAR elements, deepen the normalized IR with reusable reference objects:

```text
ARXMLReference
├── raw_ref
├── package_path
├── uuid
├── resolved_kind
├── resolved_name
└── source provenance
```

Add:

- Package-path indexing for `AR-PACKAGE` and nested elements.
- `DEST`-aware reference resolution.
- Cross-file reference resolution using absolute paths, UUIDs, and package paths.
- Explicit unresolved/ambiguous reference diagnostics.
- A source-to-target mapping record for every emitted FLYNC object.
- Deterministic naming for collisions without losing the original AUTOSAR identity.

Gate:

- No communication object may be emitted from a short name that resolves to multiple AUTOSAR objects.
- Every generated object must be traceable to an ARXML source file and element path.
- Synthetic tests cover same short names in different packages, forward references, missing references, and cross-file references.

### Layer B: PDU, Signal, and Data-Type Foundation

Implement this layer before Ethernet or SOME/IP deployment because both depend on it.

#### Source concepts to inventory

- `IMPLEMENTED-DATA-TYPE`
- `APPLICATION-PRIMITIVE-DATA-TYPE`
- `SW-DATA-DEF-PROPS`
- `DATA-CONSTR`
- `COMPU-METHOD`
- `I-SIGNAL`
- `I-SIGNAL-I-PDU`
- `PDU-TO-FRAME-MAPPING`
- `I-PDU`
- `SIGNAL-TO-I-PDU-MAPPING`
- `SIGNAL-GROUP`

#### FLYNC targets

- `Signal`
- `SignalInstance`
- `StandardPDU`
- `PDUInstance`
- `CANFrame`, `CANFDFrame`, and `LINFrame`
- Existing value-encoding and scaling structures.

#### Required behavior

- Map bit length, start position, byte order, signedness, factor, offset, unit, and limits.
- Map raw-to-physical conversion only when the ARXML conversion method is understood.
- Preserve unsupported conversion methods as diagnostics with source provenance.
- Detect overlapping signals and signals outside PDU/frame bounds before model creation.
- Preserve multiplexing and signal groups where the FLYNC model supports them.
- Never default a missing byte order, factor, offset, or limit to a guessed engineering value without a diagnostic.

Gate:

- A synthetic CAN frame with two signals loads into a valid FLYNC `CANFrame` and `StandardPDU`.
- Intel/little-endian and Motorola/big-endian cases are tested separately.
- Scaling and limits round-trip through the FLYNC model.
- Invalid overlap and unresolved PDU references fail with actionable diagnostics.

### Layer C: Ethernet Layer 2

Map physical and frame-level Ethernet semantics into FLYNC.

#### Source concepts to inventory

- Ethernet clusters and physical channels.
- Ethernet communication connectors and ECU-to-channel references.
- `ETHERNET-FRAME`
- Ethernet frame-to-PDU mappings.
- VLAN and priority configuration.
- Switches, switch ports, bridge/forwarding relationships.
- Ethernet multicast and broadcast definitions.

#### FLYNC targets

- `EthernetInterfaceConfig`
- `ECUPort`
- `EthernetTopology`
- `EthernetPointToPointConnection`
- `EthernetMultidropConnection`
- VLAN and multicast model types.
- Ethernet PDUs and frame/PDU placement models where supported.

#### Required behavior

- Distinguish physical ECU ports, controller interfaces, switch ports, and virtual interfaces.
- Emit system topology only when both endpoints resolve to real FLYNC ports.
- Map VLAN IDs and PCP/priority values from explicit source configuration.
- Preserve link speed, PHY mode, duplex, and role only when the source provides compatible values.
- Do not treat an AUTOSAR communication channel as proof of a physical cable connection.
- Report topology links that cannot be resolved instead of creating guessed links.

Gate:

- Synthetic two-ECU Ethernet extract produces two ports and one validated FLYNC point-to-point connection.
- A switch topology fixture produces switch ports and valid internal connections.
- VLAN and multicast fixtures appear in generated FLYNC files.
- The browser diagram visibly changes when L2 links are added.

### Layer D: Ethernet Layer 3 and Socket Deployment

Map network-layer and transport-layer deployment after L2 identities are stable.

#### Source concepts to inventory

- IPv4 and IPv6 address assignments.
- Network endpoints and subnet references.
- UDP/TCP port prototypes and socket addresses.
- Transport protocol configuration.
- Multicast endpoint configuration.
- TCP options and transport timing where represented.

#### FLYNC targets

- `VirtualControllerInterface`
- `IPv4AddressEndpoint` and `IPv6AddressEndpoint`
- `SocketUDP` and `SocketTCP`
- `SocketContainer`
- TCP/UDP option profiles.

#### Required behavior

- Bind each IP endpoint to the correct FLYNC virtual interface.
- Validate subnet, address family, protocol, and port consistency.
- Preserve multicast versus unicast semantics.
- Resolve socket-to-PDU and socket-to-service references through the shared reference index.
- Reject duplicate socket identities and conflicting endpoint assignments.

Gate:

- Synthetic IPv4/IPv6 UDP/TCP fixtures generate valid FLYNC sockets.
- Multicast socket generation is tested.
- Invalid subnet, duplicate port, and wrong endpoint-family cases produce diagnostics.
- Generated workspace reloads through `FLYNCWorkspace.load_workspace()`.

### Layer E: SOME/IP Service Model

Implement SOME/IP only after data types, PDUs, IP endpoints, and sockets are available.

#### Source concepts to inventory

- Service interfaces and versions.
- Methods and request/response data.
- Events, fields, and event groups.
- Method/event/field identifiers.
- Service instances and deployments.
- SOME/IP-SD offer/find/subscribe configuration.
- UDP/TCP transport selection.

#### FLYNC targets

- `SOMEIPServiceInterface`
- SOME/IP methods, events, fields, and event groups.
- `SOMEIPConfig` and SD timing/configuration.
- `SOMEIPServiceProvider`
- `SOMEIPServiceConsumer`
- `SocketUDP`/`SocketTCP` deployments.

#### Required behavior

- Map service ID, major version, minor version, method/event/field IDs, and instance ID.
- Resolve event-group members against the service interface.
- Map service payload types to the PDU/data-type layer rather than duplicating type logic.
- Validate provider/consumer deployment references.
- Preserve SOME/IP-SD timing values only when explicitly present.
- Reject duplicate identifiers and incompatible service versions.

Gate:

- A synthetic service with one method, event, field, and event group validates as `SOMEIPServiceInterface`.
- Provider and consumer deployments bind to the correct sockets.
- Missing event-group members and duplicate IDs are rejected.
- The generated browser diagram includes service/deployment annotations only after L3 validation passes.

### Layer F: Diagnostics and DoIP/UDS

Implement diagnostics after L3 sockets and service deployment are stable.

#### Source concepts to inventory

- DoIP entities, logical addresses, discovery, and routing activation.
- Diagnostic sessions.
- Security access levels.
- DIDs and data records.
- Routines.
- DTCs and status data.
- Request/response service definitions.

#### FLYNC targets

- `DiagnosticsConfig`
- DoIP configuration and deployments.
- `UDSConfig`, servers, sessions, services, DIDs, routines, and DTC records.
- DoIP TCP/UDP sockets.

#### Required behavior

- Resolve diagnostic services and identifiers through the shared reference layer.
- Preserve session/security preconditions.
- Map DIDs, data records, routines, and DTC status fields only when their encodings are understood.
- Report unsupported OEM-specific diagnostic extensions explicitly.
- Never imply that a generated diagnostic description is wire-compatible without validation evidence.

Gate:

- A synthetic DoIP/UDS server with one session, DID, routine, and DTC validates.
- Diagnostic sockets bind to the correct ECU/interface.
- Duplicate DIDs, invalid references, and unsupported encodings produce diagnostics.

### Web and Artifact Acceptance

Every completed layer must be visible in both generated artifacts:

- The generated FLYNC workspace ZIP contains the corresponding `communication/`, `ecus/`, and `topology/` files.
- The browser diagram shows only relationships that were actually resolved.
- The browser status log reports the current mapping stage and object counts.
- Download links remain available for the FLYNC ZIP, SVG, HTML, and PUML outputs.

### Recommended Delivery Sequence

1. Shared references and provenance.
2. Data types, signals, PDUs, and frame placements.
3. CAN and LIN frames/controllers/schedules.
4. Ethernet L2 channels, ports, VLANs, and topology links.
5. Ethernet L3 addresses, sockets, and transport deployments.
6. SOME/IP interfaces and service deployments.
7. DoIP/UDS diagnostics.
8. Browser diagram annotations and artifact-level regression tests.

Do not start SOME/IP or diagnostics from raw XML directly. Both should consume the shared normalized references and the already-validated data-type, PDU, socket, and deployment modules.