"""Normalized, provenance-aware AUTOSAR ARXML input representation."""

from __future__ import annotations

import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ARXMLSource:
    """Source file and stable local element path."""

    file: str
    path: str


@dataclass(frozen=True)
class ARXMLDiagnostic:
    """Conversion diagnostic retained for reporting and tests."""

    severity: str
    message: str
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLController:
    """Communication controller and only the channels it owns."""

    name: str
    kind: str
    interfaces: tuple[str, ...] = ()
    bus_names: tuple[str, ...] = ()
    ethernet_interfaces: tuple["ARXLEthernetInterface", ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXLEcu:
    """ECU instance with controller ownership preserved."""

    name: str
    controllers: tuple[ARXMLController, ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLBus:
    """Minimal CAN or LIN channel definition."""

    name: str
    kind: str
    baud_rate: int | None = None
    fd_baud_rate: int | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLSocket:
    """Explicit UDP or TCP socket endpoint owned by an Ethernet channel."""

    name: str
    protocol: str
    address: str | None = None
    port: int | None = None
    tcp_profile: int | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLVirtualInterface:
    """VLAN-tagged or untagged logical Ethernet interface with explicit IP endpoints."""

    name: str
    vlan_id: int | None = None
    ipv4_addresses: tuple[tuple[str, str], ...] = ()
    ipv6_addresses: tuple[tuple[str, int], ...] = ()
    sockets: tuple[ARXMLSocket, ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXLEthernetInterface:
    """Physical Ethernet channel data owned by one communication controller."""

    name: str
    mac_address: str | None = None
    virtual_interfaces: tuple[ARXMLVirtualInterface, ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLTopologyConnection:
    """Raw Ethernet topology endpoints retained for conservative diagnostics."""

    name: str
    endpoint_refs: tuple[str, ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLSignal:
    """Signal definition and the source-level properties needed for PDU mapping."""

    name: str
    length: int | None = None
    source: ARXMLSource | None = None
    data_type_ref: str | None = None
    compu_method_ref: str | None = None
    unit: str | None = None
    lower_limit: float | None = None
    upper_limit: float | None = None


@dataclass(frozen=True)
class ARXMLBaseDataType:
    """Explicit AUTOSAR base data type information used for signal typing."""

    name: str
    bit_length: int | None = None
    encoding: str | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLCompuMethod:
    """Linear AUTOSAR COMPU-METHOD information when its rational formula is known."""

    name: str
    factor: float | None = None
    offset: float | None = None
    unit: str | None = None
    lower_limit: float | None = None
    upper_limit: float | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLFrame:
    """Explicit CAN or LIN frame placement metadata."""

    name: str
    kind: str
    bus_name: str | None = None
    frame_id: int | None = None
    id_format: str | None = None
    length: int | None = None
    pdu_ref: str | None = None
    bit_rate_switch: bool | None = None
    error_state_indicator: bool | None = None
    checksum_type: str | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLPdu:
    """PDU definition with raw signal references and placement metadata."""

    name: str
    length: int | None = None
    signal_refs: tuple[str, ...] = ()
    placements: tuple[tuple[str, int | None, str | None], ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLPduFrameMapping:
    """Explicit AUTOSAR PDU-to-frame placement reference."""

    frame_ref: str | None
    pdu_ref: str | None
    bit_position: int | None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLSomeIPElement:
    """Explicit SOME/IP method, event, or field identifier."""

    name: str
    kind: str
    identifier: int | None = None
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLSomeIPService:
    """Explicit SOME/IP service-interface metadata and member identifiers."""

    name: str
    service_id: int | None = None
    major_version: int | None = None
    minor_version: int | None = None
    methods: tuple[ARXMLSomeIPElement, ...] = ()
    events: tuple[ARXMLSomeIPElement, ...] = ()
    fields: tuple[ARXMLSomeIPElement, ...] = ()
    eventgroups: tuple[tuple[str, int | None, tuple[str, ...]], ...] = ()
    source: ARXMLSource | None = None


@dataclass(frozen=True)
class ARXMLDiagnosticInventory:
    """Explicit diagnostic identifier retained until a safe FLYNC mapping exists."""

    kind: str
    name: str
    identifier: int | None = None
    payload_length: int | None = None
    source: ARXMLSource | None = None


@dataclass
class ARXMLDocument:
    """Merged ARXML input with references, schema metadata, and diagnostics."""

    ecus: list[ARXLEcu] = field(default_factory=list)
    buses: list[ARXMLBus] = field(default_factory=list)
    signals: list[ARXMLSignal] = field(default_factory=list)
    pdus: list[ARXMLPdu] = field(default_factory=list)
    base_data_types: list[ARXMLBaseDataType] = field(default_factory=list)
    compu_methods: list[ARXMLCompuMethod] = field(default_factory=list)
    frames: list[ARXMLFrame] = field(default_factory=list)
    pdu_frame_mappings: list[ARXMLPduFrameMapping] = field(default_factory=list)
    someip_services: list[ARXMLSomeIPService] = field(default_factory=list)
    diagnostics_inventory: list[ARXMLDiagnosticInventory] = field(default_factory=list)
    topology_connections: list[ARXMLTopologyConnection] = field(default_factory=list)
    references: dict[str, ARXMLSource] = field(default_factory=dict)
    namespaces: tuple[str, ...] = ()
    schema_versions: tuple[str, ...] = ()
    diagnostics: list[ARXMLDiagnostic] = field(default_factory=list)


def local_name(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def short_name(element: ElementTree.Element) -> str | None:
    """Read a direct SHORT-NAME child."""
    for child in element:
        if local_name(child.tag) == "SHORT-NAME" and child.text:
            return child.text.strip()
    return None


def _source(path: Path, element: ElementTree.Element, index: int) -> ARXMLSource:
    return ARXMLSource(str(path), f"/{local_name(element.tag)}[{index}]")


def _descendant_text(element: ElementTree.Element, names: set[str]) -> str | None:
    for child in element.iter():
        if local_name(child.tag) in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def _integer_text(element: ElementTree.Element, names: set[str]) -> int | None:
    """Read an integer-valued descendant when it is explicit and parseable."""
    value = _descendant_text(element, names)
    if value is None:
        return None
    try:
        return int(value, 0)
    except ValueError:
        try:
            return int(float(value))
        except ValueError:
            return None


def _float_text(element: ElementTree.Element, names: set[str]) -> float | None:
    value = _descendant_text(element, names)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _boolean_text(element: ElementTree.Element, names: set[str]) -> bool | None:
    value = _descendant_text(element, names)
    if value is None:
        return None
    normalized = value.upper()
    if normalized in {"TRUE", "1", "YES"}:
        return True
    if normalized in {"FALSE", "0", "NO"}:
        return False
    return None


def _reference_text(element: ElementTree.Element, names: set[str]) -> str | None:
    value = _descendant_text(element, names)
    return value.rsplit("/", 1)[-1] if value else None


def _text_values(element: ElementTree.Element, names: set[str]) -> tuple[str, ...]:
    """Return unique non-empty descendant text values for selected tags."""
    values: list[str] = []
    for child in element.iter():
        if local_name(child.tag) in names and child.text and child.text.strip():
            value = child.text.strip()
            if value not in values:
                values.append(value)
    return tuple(values)


def _socket(path: Path, element: ElementTree.Element, index: int, protocol: str, address: str | None = None) -> ARXMLSocket | None:
    name = short_name(element)
    if not name:
        return None
    port = _integer_text(element, {"PORT-NUMBER", "PORT", "UDP-PORT", "TCP-PORT"})
    tcp_profile = _integer_text(element, {"TCP-PROFILE", "TCP-PROFILE-ID", "TCP-OPTION-REF"})
    return ARXMLSocket(
        name,
        protocol,
        address or _descendant_text(element, {"IPV-4-ADDRESS", "IPV-6-ADDRESS", "ADDRESS"}),
        port,
        tcp_profile,
        _source(path, element, index),
    )


def _virtual_interface(path: Path, element: ElementTree.Element, index: int) -> ARXMLVirtualInterface | None:
    name = short_name(element)
    if not name:
        return None
    vlan_id = _integer_text(element, {"VLAN-ID", "VLAN-IDENTIFIER"})
    ipv4: list[tuple[str, str]] = []
    ipv6: list[tuple[str, int]] = []
    sockets: list[ARXMLSocket] = []

    def add_socket(socket: ARXMLSocket | None) -> None:
        if socket is None:
            return
        for position, previous in enumerate(sockets):
            if previous.name == socket.name and previous.protocol == socket.protocol:
                if socket.address is not None or previous.address is None:
                    sockets[position] = socket
                return
        sockets.append(socket)

    for child_index, child in enumerate(element.iter(), 1):
        tag = local_name(child.tag)
        if tag in {"IPV-4-EXT", "IPV4-ADDRESS", "IPV4-ENDPOINT"}:
            address = _descendant_text(child, {"IPV-4-ADDRESS", "IPV4-ADDRESS", "ADDRESS"})
            netmask = _descendant_text(child, {"IPV-4-SUBNET-MASK", "IPV4-SUBNET-MASK", "SUBNET-MASK"})
            if address and netmask:
                ipv4.append((address, netmask))
            for socket_index, socket_element in enumerate(child.iter(), 1):
                if local_name(socket_element.tag) in {"UDP-SOCKET", "UDP-SOCKET-ADDRESS"}:
                    add_socket(_socket(path, socket_element, socket_index, "udp", address))
                elif local_name(socket_element.tag) in {"TCP-SOCKET", "TCP-SOCKET-ADDRESS"}:
                    add_socket(_socket(path, socket_element, socket_index, "tcp", address))
        elif tag in {"IPV-6-EXT", "IPV6-ADDRESS", "IPV6-ENDPOINT"}:
            address = _descendant_text(child, {"IPV-6-ADDRESS", "IPV6-ADDRESS", "ADDRESS"})
            prefix = _integer_text(child, {"IPV-6-PREFIX-LENGTH", "IPV6-PREFIX-LENGTH", "PREFIX-LENGTH"})
            if address and prefix is not None:
                ipv6.append((address, prefix))
            for socket_index, socket_element in enumerate(child.iter(), 1):
                if local_name(socket_element.tag) in {"UDP-SOCKET", "UDP-SOCKET-ADDRESS"}:
                    add_socket(_socket(path, socket_element, socket_index, "udp", address))
                elif local_name(socket_element.tag) in {"TCP-SOCKET", "TCP-SOCKET-ADDRESS"}:
                    add_socket(_socket(path, socket_element, socket_index, "tcp", address))
        elif tag in {"UDP-SOCKET", "UDP-SOCKET-ADDRESS"}:
            add_socket(_socket(path, child, child_index, "udp"))
        elif tag in {"TCP-SOCKET", "TCP-SOCKET-ADDRESS"}:
            add_socket(_socket(path, child, child_index, "tcp"))
    return ARXMLVirtualInterface(
        name, vlan_id, tuple(dict.fromkeys(ipv4)), tuple(dict.fromkeys(ipv6)), tuple(sockets), _source(path, element, index)
    )


def _ethernet_interface(path: Path, element: ElementTree.Element, index: int) -> ARXLEthernetInterface | None:
    name = short_name(element)
    if not name:
        return None
    virtual_interfaces = tuple(
        interface
        for child_index, child in enumerate(element.iter(), 1)
        if local_name(child.tag) in {"VLAN", "VLAN-INTERFACE", "VIRTUAL-ETHERNET-INTERFACE", "ETHERNET-VIRTUAL-CHANNEL"}
        for interface in [_virtual_interface(path, child, child_index)]
        if interface
    )
    return ARXLEthernetInterface(
        name,
        _descendant_text(element, {"MAC-ADDRESS", "PHYSICAL-ADDRESS"}),
        virtual_interfaces,
        _source(path, element, index),
    )


def _rational_coefficients(element: ElementTree.Element) -> tuple[float | None, float | None]:
    values: list[float] = []
    for child in element.iter():
        if local_name(child.tag) not in {"V", "VALUE"} or not child.text:
            continue
        try:
            values.append(float(child.text.strip()))
        except ValueError:
            continue
    if len(values) < 2 or values[1] == 0:
        return None, None
    return values[1], values[0]


def _controller(path: Path, element: ElementTree.Element, index: int) -> ARXMLController | None:
    controller_name = short_name(element)
    if not controller_name:
        return None
    names = {local_name(child.tag) for child in element.iter()}
    kind = (
        "ethernet"
        if any("ETHERNET" in value for value in names)
        else "lin" if any("LIN" in value for value in names) else "can" if any("CAN" in value for value in names) else "unknown"
    )
    interfaces: list[str] = []
    buses: list[str] = []
    ethernet_interfaces: list[ARXLEthernetInterface] = []
    channel_tags = {
        "ETHERNET-PHYSICAL-CHANNEL": "interface",
        "CAN-CLUSTER": "bus",
        "CAN-CHANNEL": "bus",
        "LIN-CLUSTER": "bus",
        "LIN-CHANNEL": "bus",
    }
    for child in element.iter():
        child_name = short_name(child)
        role = channel_tags.get(local_name(child.tag))
        if child_name and role == "interface":
            interfaces.append(child_name)
            interface = _ethernet_interface(path, child, index)
            if interface:
                ethernet_interfaces.append(interface)
        elif child_name and role == "bus":
            buses.append(child_name)
    return ARXMLController(
        controller_name,
        kind,
        tuple(dict.fromkeys(interfaces)),
        tuple(dict.fromkeys(buses)),
        tuple(ethernet_interfaces),
        _source(path, element, index),
    )


def _merge_pdu(existing: ARXMLPdu, incoming: ARXMLPdu) -> tuple[ARXMLPdu, str | None]:
    """Merge repeated PDU fragments and return a semantic conflict, if any."""
    if existing.length is not None and incoming.length is not None and existing.length != incoming.length:
        merged_length = max(existing.length, incoming.length)
        return (
            ARXMLPdu(
                name=existing.name,
                length=merged_length,
                signal_refs=tuple(dict.fromkeys(existing.signal_refs + incoming.signal_refs)),
                placements=existing.placements,
                source=existing.source,
            ),
            f"Conflicting PDU length for '{existing.name}': {existing.length} vs {incoming.length}; retained {merged_length}",
        )

    placements: dict[str, tuple[str, int | None, str | None]] = {placement[0]: placement for placement in existing.placements}
    for placement in incoming.placements:
        previous = placements.get(placement[0])
        if previous is not None and previous[1:] != placement[1:]:
            return existing, f"Conflicting PDU placement for '{existing.name}' signal '{placement[0]}'"
        placements[placement[0]] = placement

    return (
        ARXMLPdu(
            name=existing.name,
            length=existing.length if existing.length is not None else incoming.length,
            signal_refs=tuple(dict.fromkeys(existing.signal_refs + incoming.signal_refs)),
            placements=tuple(placements.values()),
            source=existing.source,
        ),
        None,
    )


def _someip_service(path: Path, element: ElementTree.Element, index: int) -> ARXMLSomeIPService | None:
    name = short_name(element)
    if not name:
        return None
    members: dict[str, list[ARXMLSomeIPElement]] = {"method": [], "event": [], "field": []}
    member_tags = {
        "method": {"SOMEIP-METHOD", "METHOD", "CLIENT-SERVER-OPERATION"},
        "event": {"SOMEIP-EVENT", "EVENT", "VARIABLE-DATA-PROTOTYPE"},
        "field": {"SOMEIP-FIELD", "FIELD"},
    }
    for member in element.iter():
        kind = next((candidate for candidate, tags in member_tags.items() if local_name(member.tag) in tags), None)
        member_name = short_name(member)
        if kind and member_name and member is not element:
            members[kind].append(
                ARXMLSomeIPElement(
                    member_name, kind, _integer_text(member, {f"{kind.upper()}-ID", "ID", "IDENTIFIER"}), _source(path, member, index)
                )
            )
    eventgroups: list[tuple[str, int | None, tuple[str, ...]]] = []
    for group in element.iter():
        if local_name(group.tag) not in {"SOMEIP-EVENTGROUP", "EVENT-GROUP", "EVENTGROUP"}:
            continue
        group_name = short_name(group)
        if not group_name:
            continue
        members_by_ref = _text_values(group, {"EVENT-REF", "FIELD-REF", "EVENT-REFERENCE", "FIELD-REFERENCE"})
        eventgroups.append(
            (
                group_name,
                _integer_text(group, {"EVENTGROUP-ID", "EVENT-GROUP-ID", "ID", "IDENTIFIER"}),
                tuple(ref.rsplit("/", 1)[-1] for ref in members_by_ref),
            )
        )
    return ARXMLSomeIPService(
        name,
        _integer_text(element, {"SERVICE-ID", "SERVICE-IDENTIFIER", "ID"}),
        _integer_text(element, {"MAJOR-VERSION", "SERVICE-MAJOR-VERSION"}),
        _integer_text(element, {"MINOR-VERSION", "SERVICE-MINOR-VERSION"}),
        tuple(members["method"]),
        tuple(members["event"]),
        tuple(members["field"]),
        tuple(eventgroups),
        _source(path, element, index),
    )


def _diagnostic_inventory(path: Path, element: ElementTree.Element, index: int) -> ARXMLDiagnosticInventory | None:
    tag = local_name(element.tag)
    kind_tags = {
        "doip": {"DOIP-ENTITY", "DOIP-SERVER", "DOIP-LOGICAL-ADDRESS"},
        "uds": {"UDS-ECU", "UDS-SERVER", "UDS-SERVICE"},
        "did": {"DATA-IDENTIFIER", "DIAGNOSTIC-DATA-IDENTIFIER", "DID"},
        "dtc": {"DIAGNOSTIC-TROUBLE-CODE", "DTC"},
    }
    kind = next((candidate for candidate, tags in kind_tags.items() if tag in tags), None)
    name = short_name(element)
    if kind is None or name is None:
        return None
    identifier_names = {
        "doip": {"LOGICAL-ADDRESS", "DOIP-LOGICAL-ADDRESS", "ADDRESS"},
        "uds": {"SERVICE-ID", "UDS-SERVICE-ID", "SID"},
        "did": {"DID", "DATA-ID", "DATA-IDENTIFIER"},
        "dtc": {"DTC", "DTC-ID", "DTC-VALUE", "CODE"},
    }
    return ARXMLDiagnosticInventory(
        kind,
        name,
        _integer_text(element, identifier_names[kind]),
        _integer_text(element, {"LENGTH", "BYTE-LENGTH", "DATA-LENGTH"}) if kind == "did" else None,
        _source(path, element, index),
    )


def parse_file(path: Path) -> ARXMLDocument:
    """Parse one ARXML document with external entity/network resolution disabled by ElementTree."""
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as exc:
        raise ValueError(f"Invalid ARXML XML in '{path}': {exc}") from exc
    namespace = root.tag.split("}", 1)[0].removeprefix("{") if "}" in root.tag else ""
    version = root.attrib.get("schema-version") or root.attrib.get("xsi:schemaLocation") or ""
    result = ARXMLDocument(namespaces=(namespace,) if namespace else (), schema_versions=(version,) if version else ())
    for index, element in enumerate(root.iter(), 1):
        source = _source(path, element, index)
        uuid = element.attrib.get("UUID")
        if uuid:
            if uuid in result.references:
                result.diagnostics.append(ARXMLDiagnostic("warning", f"Repeated UUID '{uuid}' across ARXML fragments", source))
            result.references[uuid] = source
        if local_name(element.tag) == "ECU-INSTANCE":
            ecu_name = short_name(element)
            if not ecu_name:
                raise ValueError(f"ARXML ECU-INSTANCE in '{path}' has no SHORT-NAME")
            controllers = tuple(
                controller
                for child_index, child in enumerate(element.iter(), 1)
                if local_name(child.tag) in {"COMM-CONTROLLER", "CAN-COMMUNICATION-CONTROLLER", "ETHERNET-COMMUNICATION-CONTROLLER"}
                for controller in [_controller(path, child, child_index)]
                if controller
            )
            result.ecus.append(ARXLEcu(ecu_name, controllers, source))
            for controller in controllers:
                for interface in controller.ethernet_interfaces:
                    for virtual in interface.virtual_interfaces:
                        address_count = len(virtual.ipv4_addresses) + len(virtual.ipv6_addresses)
                        for socket in virtual.sockets:
                            if socket.port is None or (socket.address is None and address_count != 1):
                                result.diagnostics.append(
                                    ARXMLDiagnostic(
                                        "warning",
                                        f"Socket '{socket.name}' lacks an explicit, unambiguous endpoint address or port; socket was not emitted",
                                        socket.source,
                                    )
                                )
                            elif socket.protocol == "tcp" and socket.tcp_profile is None:
                                result.diagnostics.append(
                                    ARXMLDiagnostic(
                                        "warning",
                                        f"TCP socket '{socket.name}' has no explicit TCP profile; socket was not emitted",
                                        socket.source,
                                    )
                                )
        tag = local_name(element.tag)
        element_name = short_name(element)
        if tag in {"CAN-CLUSTER", "CAN-CHANNEL", "LIN-CLUSTER", "LIN-CHANNEL"}:
            if element_name:
                raw_rate = _descendant_text(element, {"CAN-BAUDRATE", "BAUDRATE", "LIN-SPEED", "BAUD-RATE"})
                rate = int(float(raw_rate)) if raw_rate and raw_rate.replace(".", "", 1).isdigit() else None
                raw_fd_rate = _descendant_text(element, {"CAN-FD-BAUDRATE", "CAN-FD-DATA-BAUDRATE", "DATA-BAUDRATE"})
                fd_rate = int(float(raw_fd_rate)) if raw_fd_rate and raw_fd_rate.replace(".", "", 1).isdigit() else None
                result.buses.append(ARXMLBus(element_name, "can" if "CAN" in tag else "lin", rate, fd_rate, source))
        if tag == "I-SIGNAL" and element_name:
            result.signals.append(
                ARXMLSignal(
                    element_name,
                    _integer_text(element, {"LENGTH"}),
                    source,
                    _reference_text(element, {"BASE-TYPE-REF", "DATA-TYPE-REF", "IMPLEMENTED-DATA-TYPE-REF"}),
                    _reference_text(element, {"COMPU-METHOD-REF"}),
                    _reference_text(element, {"UNIT-REF"}),
                    _float_text(element, {"LOWER-LIMIT"}),
                    _float_text(element, {"UPPER-LIMIT"}),
                )
            )
        if tag in {"SW-BASE-TYPE", "BASE-TYPE"} and element_name:
            result.base_data_types.append(
                ARXMLBaseDataType(
                    element_name,
                    _integer_text(element, {"SIZE", "BASE-TYPE-SIZE", "BIT-LENGTH"}),
                    _descendant_text(element, {"ENCODING"}),
                    source,
                )
            )
        if tag == "COMPU-METHOD" and element_name:
            factor, offset = _rational_coefficients(element)
            result.compu_methods.append(
                ARXMLCompuMethod(
                    element_name,
                    factor,
                    offset,
                    _reference_text(element, {"UNIT-REF"}),
                    _float_text(element, {"LOWER-LIMIT"}),
                    _float_text(element, {"UPPER-LIMIT"}),
                    source,
                )
            )
        if tag in {"I-SIGNAL-I-PDU", "PDU"} and element_name:
            refs: list[str] = []
            placements: list[tuple[str, int | None, str | None]] = []
            for mapping in element.iter():
                if local_name(mapping.tag) != "I-SIGNAL-TO-I-PDU-MAPPING":
                    continue
                signal_ref = _descendant_text(mapping, {"I-SIGNAL-REF"})
                if not signal_ref:
                    continue
                signal_name = signal_ref.rsplit("/", 1)[-1]
                refs.append(signal_name)
                placements.append(
                    (
                        signal_name,
                        _integer_text(mapping, {"START-POSITION", "BIT-POSITION"}),
                        _descendant_text(mapping, {"PACKING-BYTE-ORDER", "BYTE-ORDER"}),
                    )
                )
            result.pdus.append(ARXMLPdu(element_name, _integer_text(element, {"LENGTH"}), tuple(dict.fromkeys(refs)), tuple(placements), source))
        if tag in {"CAN-FRAME", "LIN-FRAME"} and element_name:
            kind = "can" if tag == "CAN-FRAME" else "lin"
            pdu_ref = _reference_text(element, {"PDU-REF", "I-PDU-REF"})
            result.frames.append(
                ARXMLFrame(
                    element_name,
                    kind,
                    _reference_text(element, {"BUS-REF", "CAN-CLUSTER-REF", "LIN-CLUSTER-REF", "CHANNEL-REF"}),
                    _integer_text(element, {"CAN-ID", "LIN-ID", "FRAME-ID"}),
                    _descendant_text(element, {"ID-FORMAT", "CAN-ADDRESSING-FORMAT"}),
                    _integer_text(element, {"LENGTH", "BYTE-LENGTH"}),
                    pdu_ref,
                    _boolean_text(element, {"BIT-RATE-SWITCH", "BRS"}),
                    _boolean_text(element, {"ERROR-STATE-INDICATOR", "ESI"}),
                    _descendant_text(element, {"CHECKSUM-TYPE", "CHECKSUM"}),
                    source,
                )
            )
            if pdu_ref:
                result.pdu_frame_mappings.append(ARXMLPduFrameMapping(element_name, pdu_ref, 0, source))
        if tag == "CAN-FD-FRAME" and element_name:
            pdu_ref = _reference_text(element, {"PDU-REF", "I-PDU-REF"})
            result.frames.append(
                ARXMLFrame(
                    element_name,
                    "can_fd",
                    _reference_text(element, {"BUS-REF", "CAN-CLUSTER-REF", "CHANNEL-REF"}),
                    _integer_text(element, {"CAN-ID", "FRAME-ID"}),
                    _descendant_text(element, {"ID-FORMAT", "CAN-ADDRESSING-FORMAT"}),
                    _integer_text(element, {"LENGTH", "BYTE-LENGTH"}),
                    pdu_ref,
                    _boolean_text(element, {"BIT-RATE-SWITCH", "BRS"}),
                    _boolean_text(element, {"ERROR-STATE-INDICATOR", "ESI"}),
                    None,
                    source,
                )
            )
            if pdu_ref:
                result.pdu_frame_mappings.append(ARXMLPduFrameMapping(element_name, pdu_ref, 0, source))
        if tag == "PDU-TO-FRAME-MAPPING":
            result.pdu_frame_mappings.append(
                ARXMLPduFrameMapping(
                    _reference_text(element, {"FRAME-REF", "CAN-FRAME-REF", "LIN-FRAME-REF"}),
                    _reference_text(element, {"PDU-REF", "I-PDU-REF"}),
                    _integer_text(element, {"START-POSITION", "BIT-POSITION"}),
                    source,
                )
            )
        if tag in {"ETHERNET-TOPOLOGY-CONNECTION", "ETHERNET-CHANNEL-CONNECTION", "PHYSICAL-CHANNEL-CONNECTION"}:
            connection_name = element_name or f"connection_{index}"
            endpoint_refs = _text_values(
                element, {"PHYSICAL-CHANNEL-REF", "ETHERNET-PHYSICAL-CHANNEL-REF", "ECU-PORT-REF", "PORT-REF", "ENDPOINT-REF"}
            )
            result.topology_connections.append(ARXMLTopologyConnection(connection_name, endpoint_refs, source))
        if tag in {"SOMEIP-SERVICE-INTERFACE", "SOMEIP-SERVICE-INTERFACE-DEPLOYMENT"}:
            service = _someip_service(path, element, index)
            if service:
                result.someip_services.append(service)
        if tag in {
            "DOIP-TP-CONFIG",
            "UDS-ECU-REF",
            "DIAGNOSTIC-EVENT",
            "DOIP-ENTITY",
            "DOIP-SERVER",
            "DOIP-LOGICAL-ADDRESS",
            "UDS-ECU",
            "UDS-SERVER",
            "UDS-SERVICE",
            "DATA-IDENTIFIER",
            "DIAGNOSTIC-DATA-IDENTIFIER",
            "DID",
            "DIAGNOSTIC-TROUBLE-CODE",
            "DTC",
        }:
            inventory = _diagnostic_inventory(path, element, index)
            if inventory:
                result.diagnostics_inventory.append(inventory)
            else:
                result.diagnostics.append(ARXMLDiagnostic("warning", f"Unsupported ARXML element for current converter scope: {tag}", source))
    return result


def merge(documents: list[ARXMLDocument]) -> ARXMLDocument:
    """Merge fragments deterministically and reject conflicting controller definitions."""
    result = ARXMLDocument()
    ecu_map: dict[str, ARXLEcu] = {}
    bus_map: dict[tuple[str, str], ARXMLBus] = {}
    for document in documents:
        result.namespaces = tuple(dict.fromkeys(result.namespaces + document.namespaces))
        result.schema_versions = tuple(dict.fromkeys(result.schema_versions + document.schema_versions))
        result.references.update(document.references)
        result.diagnostics.extend(document.diagnostics)
        result.signals.extend(document.signals)
        result.base_data_types.extend(document.base_data_types)
        result.compu_methods.extend(document.compu_methods)
        result.frames.extend(document.frames)
        result.pdu_frame_mappings.extend(document.pdu_frame_mappings)
        result.someip_services.extend(document.someip_services)
        result.diagnostics_inventory.extend(document.diagnostics_inventory)
        result.topology_connections.extend(document.topology_connections)
        for bus in document.buses:
            key = (bus.kind, bus.name)
            previous = bus_map.get(key)
            if previous and previous.baud_rate != bus.baud_rate:
                result.diagnostics.append(ARXMLDiagnostic("error", f"Conflicting {bus.kind} bus definition '{bus.name}'", bus.source))
            bus_map[key] = previous or bus
        for pdu in document.pdus:
            existing = next((item for item in result.pdus if item.name == pdu.name), None)
            if existing is None:
                result.pdus.append(pdu)
            else:
                merged_pdu, conflict = _merge_pdu(existing, pdu)
                if conflict is not None:
                    result.diagnostics.append(ARXMLDiagnostic("warning", conflict, pdu.source))
                    result.pdus[result.pdus.index(existing)] = merged_pdu
                else:
                    result.pdus[result.pdus.index(existing)] = merged_pdu
        for ecu in document.ecus:
            previous_ecu = ecu_map.get(ecu.name)
            if previous_ecu is None:
                ecu_map[ecu.name] = ecu
                continue
            controllers = {item.name: item for item in previous_ecu.controllers}
            for controller in ecu.controllers:
                old = controllers.get(controller.name)
                if old is None:
                    controllers[controller.name] = controller
                    continue
                if old.kind != controller.kind or old.bus_names != controller.bus_names:
                    result.diagnostics.append(ARXMLDiagnostic("error", f"Conflicting controller definition '{controller.name}'", controller.source))
                    continue
                controllers[controller.name] = ARXMLController(
                    controller.name,
                    controller.kind,
                    tuple(dict.fromkeys(old.interfaces + controller.interfaces)),
                    old.bus_names,
                    tuple({interface.name: interface for interface in old.ethernet_interfaces + controller.ethernet_interfaces}.values()),
                    old.source,
                )
            ecu_map[ecu.name] = ARXLEcu(ecu.name, tuple(controllers[name] for name in sorted(controllers)), previous_ecu.source)
    result.ecus = [ecu_map[name] for name in sorted(ecu_map)]
    result.buses = [bus_map[key] for key in sorted(bus_map)]
    result.signals = sorted({signal.name: signal for signal in result.signals}.values(), key=lambda signal: signal.name)
    result.base_data_types = sorted({item.name: item for item in result.base_data_types}.values(), key=lambda item: item.name)
    result.compu_methods = sorted({item.name: item for item in result.compu_methods}.values(), key=lambda item: item.name)
    result.frames.sort(key=lambda frame: frame.name)
    result.pdu_frame_mappings.sort(key=lambda mapping: (mapping.frame_ref or "", mapping.pdu_ref or "", mapping.bit_position or -1))
    result.pdus.sort(key=lambda pdu: pdu.name)
    result.topology_connections.sort(key=lambda connection: connection.name)
    result.someip_services.sort(key=lambda service: service.name)
    result.diagnostics_inventory.sort(key=lambda item: (item.kind, item.name))
    known_interfaces = {interface for ecu in result.ecus for controller in ecu.controllers for interface in controller.interfaces}
    for connection in result.topology_connections:
        unresolved = sorted(set(connection.endpoint_refs) - known_interfaces)
        if unresolved:
            result.diagnostics.append(
                ARXMLDiagnostic(
                    "warning",
                    f"Ethernet topology connection '{connection.name}' references unresolved endpoint(s): {unresolved}; topology was not emitted",
                    connection.source,
                )
            )
        else:
            result.diagnostics.append(
                ARXMLDiagnostic(
                    "warning",
                    f"Ethernet topology connection '{connection.name}' is not emitted because ECU port/link semantics are not explicit",
                    connection.source,
                )
            )
    signal_names = {signal.name for signal in result.signals}
    for pdu in result.pdus:
        missing = sorted(set(pdu.signal_refs) - signal_names)
        if missing:
            result.diagnostics.append(ARXMLDiagnostic("warning", f"PDU '{pdu.name}' references unresolved signal(s): {missing}", pdu.source))
    return result


def discover_arxml_files(config_path: str | Path) -> list[Path]:
    """Return sorted ARXML files from one file or a directory."""
    path = Path(config_path)
    if path.is_file():
        if path.suffix.lower() != ".arxml":
            raise ValueError(f"ARXML input must have an .arxml extension: '{path}'")
        return [path]
    if path.is_dir():
        files = sorted(path.rglob("*.arxml"))
        if not files:
            raise ValueError(f"No .arxml files found under '{path}'")
        return files
    raise FileNotFoundError(f"ARXML input does not exist: '{path}'")
