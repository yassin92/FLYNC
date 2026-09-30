"""First-draft AUTOSAR ARXML to FLYNC workspace converter."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from flync.model import FLYNCModel
from flync.model.flync_4_diagnostics.uds.datatypes import DiagDataRecord
from flync.model.flync_4_ecu.sockets import SocketTCP, SocketUDP
from flync.model.flync_4_signal import SignalInstance, StandardPDU
from flync.model.flync_4_signal.frame import CANFDFrame, CANFrame, LINFrame
from flync.model.flync_4_signal.pdu import PDUInstance
from flync.model.flync_4_signal.signal import Signal as FLYNCSignal
from flync.model.flync_4_signal.signal import SignalDataType
from flync.model.flync_4_someip import (
    SOMEIPEvent,
    SOMEIPField,
    SOMEIPRequestResponseMethod,
)
from flync.sdk.helpers.generation_helpers import dump_flync_workspace

from ..base.base_converter import BaseConverter
from ..registry import hookimpl
from .arxml_ir import (
    ARXMLBaseDataType,
    ARXMLCompuMethod,
    ARXMLDiagnostic,
    ARXMLDocument,
    ARXMLSignal,
    ARXMLSomeIPElement,
    ARXMLSomeIPService,
)
from .arxml_ir import discover_arxml_files as discover_ir_files
from .arxml_ir import merge, parse_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ARXLEcu:
    """Small normalized ECU representation used by the first importer slice."""

    name: str
    controller_names: tuple[str, ...] = ()
    interface_names: tuple[str, ...] = ()


def _local_name(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _short_name(element: ElementTree.Element) -> str | None:
    """Return the first direct SHORT-NAME value of an element."""
    for child in element:
        if _local_name(child.tag) == "SHORT-NAME" and child.text:
            return child.text.strip()
    return None


def _descendant_names(element: ElementTree.Element, tag_names: set[str]) -> tuple[str, ...]:
    """Collect deterministic, unique SHORT-NAMEs below selected element types."""
    names: list[str] = []
    for child in element.iter():
        if _local_name(child.tag) not in tag_names:
            continue
        name = _short_name(child)
        if name and name not in names:
            names.append(name)
    return tuple(names)


def parse_arxml_file(path: Path) -> ARXMLDocument:
    """Parse one ARXML file through the normalized IR."""
    return parse_file(path)


def discover_arxml_files(config_path: str | Path) -> list[Path]:
    """Return sorted ARXML files through the normalized input layer."""
    return discover_ir_files(config_path)


def load_arxml_documents(config_path: str | Path) -> ARXMLDocument:
    """Load and merge ARXML documents through the normalized input layer."""
    document = merge([parse_file(path) for path in discover_ir_files(config_path)])
    if not document.ecus:
        raise ValueError("No ECU-INSTANCE elements found in ARXML input")
    _validate_pdu_frame_mappings(document)
    _validate_someip_records(document)
    _validate_diagnostic_inventory(document)
    errors = [diagnostic.message for diagnostic in document.diagnostics if diagnostic.severity == "error"]
    if errors:
        raise ValueError("ARXML reference conflicts: " + "; ".join(errors))
    return document


def _validate_pdu_frame_mappings(document: ARXMLDocument) -> None:
    """Resolve explicit PDU-to-frame mappings and reject ambiguous placement."""
    frames = {frame.name: frame for frame in document.frames}
    pdus = {pdu.name: pdu for pdu in document.pdus}
    seen: set[tuple[str | None, str | None, int | None]] = set()
    ranges: dict[str, list[tuple[int, int, str]]] = {}
    for mapping in document.pdu_frame_mappings:
        key = (mapping.frame_ref, mapping.pdu_ref, mapping.bit_position)
        if key in seen:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "error", f"Duplicate PDU-to-frame mapping for frame '{mapping.frame_ref}' and PDU '{mapping.pdu_ref}'", mapping.source
                )
            )
            continue
        seen.add(key)
        if mapping.frame_ref is None or mapping.pdu_ref is None or mapping.bit_position is None:
            document.diagnostics.append(
                ARXMLDiagnostic("error", "Incomplete PDU-to-frame mapping requires frame, PDU, and bit position", mapping.source)
            )
            continue
        frame = frames.get(mapping.frame_ref)
        pdu = pdus.get(mapping.pdu_ref)
        if frame is None:
            document.diagnostics.append(
                ARXMLDiagnostic("error", f"PDU-to-frame mapping references unresolved frame '{mapping.frame_ref}'", mapping.source)
            )
            continue
        if pdu is None:
            document.diagnostics.append(
                ARXMLDiagnostic("error", f"PDU-to-frame mapping references unresolved PDU '{mapping.pdu_ref}'", mapping.source)
            )
            continue
        if pdu.length is None or pdu.length <= 0 or frame.length is None or frame.length <= 0:
            document.diagnostics.append(
                ARXMLDiagnostic("error", f"PDU-to-frame mapping for frame '{frame.name}' has incomplete PDU or frame length", mapping.source)
            )
            continue
        end = mapping.bit_position + pdu.length
        if end > frame.length * 8:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "error", f"PDU '{pdu.name}' does not fit in frame '{frame.name}' at bit position {mapping.bit_position}", mapping.source
                )
            )
            continue
        frame_ranges = ranges.setdefault(frame.name, [])
        for old_start, old_end, old_pdu in frame_ranges:
            if mapping.bit_position < old_end and end > old_start:
                document.diagnostics.append(
                    ARXMLDiagnostic("error", f"PDU placement overlap in frame '{frame.name}' between '{old_pdu}' and '{pdu.name}'", mapping.source)
                )
                break
        else:
            frame_ranges.append((mapping.bit_position, end, pdu.name))


def _validate_someip_records(document: ARXMLDocument) -> None:
    """Retain completeness diagnostics on the normalized document before emission."""
    for service in document.someip_services:
        if service.service_id is None or service.major_version is None or service.minor_version is None:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "warning", f"SOME/IP service '{service.name}' lacks explicit service ID or version; it was not emitted", service.source
                )
            )
        for element in service.methods + service.events + service.fields:
            if element.identifier is None:
                document.diagnostics.append(
                    ARXMLDiagnostic(
                        "warning", f"SOME/IP {element.kind} '{element.name}' lacks a valid explicit identifier; it was not emitted", element.source
                    )
                )
        known_names = {element.name for element in service.methods + service.events + service.fields if element.identifier is not None}
        for name, identifier, members in service.eventgroups:
            if identifier is None:
                document.diagnostics.append(
                    ARXMLDiagnostic("warning", f"SOME/IP eventgroup '{name}' lacks a valid explicit identifier; it was not emitted", service.source)
                )
            missing = sorted(set(members) - known_names)
            if missing:
                document.diagnostics.append(
                    ARXMLDiagnostic(
                        "warning", f"SOME/IP eventgroup '{name}' references unknown member(s): {missing}; it was not emitted", service.source
                    )
                )


def _validate_diagnostic_inventory(document: ARXMLDocument) -> None:
    """Retain diagnostics for inventory records that cannot form a complete FLYNC object."""
    for item in document.diagnostics_inventory:
        if item.kind == "did" and (item.identifier is None or item.payload_length is None):
            document.diagnostics.append(
                ARXMLDiagnostic("warning", f"Diagnostic DID '{item.name}' has incomplete payload; it was not emitted", item.source)
            )


def _someip_timing_config() -> dict[str, object]:
    """Provide only the required neutral timing scaffolding for explicit service metadata."""
    return {
        "sd_config": {"ip_address": "239.0.0.1", "sd_timings": [{"profile_id": "arxml_default"}]},
        "someip_timings": {
            "defaults": [
                {"profile_id": "method_default", "type": "method"},
                {"profile_id": "event_default", "type": "event"},
                {"profile_id": "field_default", "type": "field"},
            ]
        },
    }


def _someip_element_payload(element: ARXMLSomeIPElement, document: ARXMLDocument) -> dict[str, object] | None:
    if element.identifier is None or not 0 < element.identifier <= 0xFFFF:
        document.diagnostics.append(
            ARXMLDiagnostic(
                "warning", f"SOME/IP {element.kind} '{element.name}' lacks a valid explicit identifier; it was not emitted", element.source
            )
        )
        return None
    if element.kind == "method":
        return SOMEIPRequestResponseMethod(name=element.name, id=element.identifier).model_dump()
    if element.kind == "event":
        return SOMEIPEvent(name=element.name, id=element.identifier).model_dump()
    return SOMEIPField(name=element.name, notifier_id=element.identifier).model_dump()


def _someip_service_payload(service: ARXMLSomeIPService, document: ARXMLDocument) -> dict[str, object] | None:
    if service.service_id is None or service.major_version is None or service.minor_version is None:
        document.diagnostics.append(
            ARXMLDiagnostic("warning", f"SOME/IP service '{service.name}' lacks explicit service ID or version; it was not emitted", service.source)
        )
        return None
    if not 0 < service.service_id <= 0xFFFF or not 0 <= service.major_version <= 0xFF or not 0 <= service.minor_version <= 0xFFFFFFFF:
        document.diagnostics.append(
            ARXMLDiagnostic("warning", f"SOME/IP service '{service.name}' has an invalid ID or version; it was not emitted", service.source)
        )
        return None
    methods = [payload for element in service.methods if (payload := _someip_element_payload(element, document)) is not None]
    events = [payload for element in service.events if (payload := _someip_element_payload(element, document)) is not None]
    fields = [payload for element in service.fields if (payload := _someip_element_payload(element, document)) is not None]
    known_elements = {element["name"]: element for element in methods + events + fields}
    eventgroups = []
    for name, identifier, members in service.eventgroups:
        if identifier is None or not 0 < identifier <= 0xFFFF:
            document.diagnostics.append(
                ARXMLDiagnostic("warning", f"SOME/IP eventgroup '{name}' lacks a valid explicit identifier; it was not emitted", service.source)
            )
            continue
        missing = sorted(set(members) - known_elements.keys())
        if missing:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "warning", f"SOME/IP eventgroup '{name}' references unknown member(s): {missing}; it was not emitted", service.source
                )
            )
            continue
        eventgroups.append({"name": name, "id": identifier, "events": [known_elements[member] for member in members]})
    return {
        "name": service.name,
        "id": service.service_id,
        "major_version": service.major_version,
        "minor_version": service.minor_version,
        "methods": methods,
        "events": events,
        "fields": fields,
        "eventgroups": eventgroups,
        "meta": {
            "type": "someip_service",
            "author": "ARXML importer",
            "compatible_flync_version": {"version": "0.0.0"},
        },
    }


def _diagnostics_payload(document: ARXMLDocument) -> dict[str, object] | None:
    dtcs = []
    dids = []
    for item in document.diagnostics_inventory:
        if item.identifier is None:
            document.diagnostics.append(
                ARXMLDiagnostic("warning", f"Diagnostic {item.kind} '{item.name}' lacks an explicit identifier; it was not emitted", item.source)
            )
            continue
        if item.kind == "dtc" and 0 <= item.identifier <= 0xFFFFFF:
            dtcs.append({"name": item.name, "dtc": item.identifier})
        elif item.kind == "did" and 0 <= item.identifier <= 0xFFFF and item.payload_length is not None and item.payload_length >= 0:
            dids.append({"name": item.name, "did": item.identifier, "read_data": DiagDataRecord(byte_length=item.payload_length).model_dump()})
        elif item.kind in {"dtc", "did"}:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "warning",
                    f"Diagnostic {item.kind} '{item.name}' has unsupported identifier or incomplete payload; it was not emitted",
                    item.source,
                )
            )
        else:
            document.diagnostics.append(
                ARXMLDiagnostic(
                    "warning", f"Diagnostic {item.kind} '{item.name}' is inventory-only; deployment semantics were not emitted", item.source
                )
            )
    if not dtcs and not dids:
        return None
    return {"version": "0.14", "uds": {"timings": {"defaults": [{"profile_id": "arxml_default"}]}, "dids": dids, "dtcs": dtcs}}


def _model_from_documents(document: ARXMLDocument) -> FLYNCModel:
    """Build the validated FLYNC model from normalized ARXML input."""
    ecus = []
    bus_names = {bus.name for bus in document.buses}
    for ecu in document.ecus:
        controller_entries = list(ecu.controllers)
        if not controller_entries:
            controller_entries = [
                type("FallbackController", (), {"name": f"{ecu.name}_controller", "interfaces": (f"{ecu.name}_ethernet0",), "bus_names": ()})()
            ]
        controllers: list[dict] = []
        for controller in controller_entries:
            can_interfaces = [{"name": f"{controller.name}_{name}", "bus_ref": name} for name in controller.bus_names if name in bus_names]
            ethernet_details = {interface.name: interface for interface in getattr(controller, "ethernet_interfaces", ())}
            ethernet_interfaces = [
                {
                    "name": name,
                    "interface_config": _ethernet_interface_config(ethernet_details.get(name), document),
                    "sockets": _ethernet_socket_containers(ethernet_details.get(name), document),
                }
                for name in controller.interfaces
            ]
            if not ethernet_interfaces and not can_interfaces:
                ethernet_interfaces = [{"name": f"{controller.name}_ethernet0", "interface_config": {}}]
            controllers.append(
                {
                    "name": controller.name,
                    "controller_metadata": {
                        "type": "embedded",
                        "author": "ARXML importer",
                        "compatible_flync_version": {"version": "0.0.0"},
                        "target_system": "unknown",
                    },
                    "ethernet_interfaces": ethernet_interfaces,
                    "can_interfaces": can_interfaces,
                }
            )
        first_controller = controller_entries[0].name
        first_interface = next(
            (interface["name"] for controller_entry in controllers for interface in controller_entry["ethernet_interfaces"]), None
        )
        ecu_payload = {
            "name": ecu.name,
            "controllers": controllers,
            "ecu_metadata": {"type": "ecu", "author": "ARXML importer", "compatible_flync_version": {"version": "0.0.0"}},
        }
        if first_interface:
            ecu_payload.update(
                {
                    "ports": [{"name": f"{ecu.name}_port0"}],
                    "topology": {
                        "connections": [
                            {
                                "type": "ecu_port_to_controller_interface",
                                "id": f"{ecu.name}_port0_to_{first_interface}",
                                "ecu_port": f"{ecu.name}_port0",
                                "controller_interface": first_interface,
                                "controller": first_controller,
                            }
                        ]
                    },
                }
            )
        ecus.append(ecu_payload)
    data_types = {item.name: item for item in document.base_data_types}
    compu_methods = {item.name: item for item in document.compu_methods}
    emitted_signals: dict[str, FLYNCSignal] = {}
    for signal in document.signals:
        converted = _to_flync_signal(signal, data_types, compu_methods, document)
        if converted is not None:
            emitted_signals[signal.name] = converted

    pdus: list[StandardPDU] = []
    for pdu in document.pdus:
        if pdu.length is None or pdu.length <= 0:
            continue
        instances: list[SignalInstance] = []
        valid = True
        for signal_name, bit_position, byte_order in pdu.placements:
            signal_instance_definition = emitted_signals.get(signal_name)
            if signal_instance_definition is None or bit_position is None or byte_order not in {"LE", "BE", "LITTLE-ENDIAN", "BIG-ENDIAN"}:
                valid = False
                document.diagnostics.append(
                    ARXMLDiagnostic("warning", f"PDU '{pdu.name}' has incomplete placement for signal '{signal_name}'", pdu.source)
                )
                continue
            instances.append(
                SignalInstance(
                    signal=signal_instance_definition, bit_position=bit_position, endianness="LE" if byte_order in {"LE", "LITTLE-ENDIAN"} else "BE"
                )
            )
        if valid and instances:
            pdus.append(StandardPDU(name=pdu.name, type="standard", length=(pdu.length + 7) // 8, signals=instances))

    pdu_names = {pdu.name for pdu in pdus}
    can_frames: dict[str, list[CANFrame | CANFDFrame]] = {bus.name: [] for bus in document.buses if bus.kind == "can" and bus.baud_rate is not None}
    lin_frames: dict[str, list[LINFrame]] = {bus.name: [] for bus in document.buses if bus.kind == "lin" and bus.baud_rate is not None}
    mappings_by_frame: dict[str, list] = {}
    for mapping in document.pdu_frame_mappings:
        if mapping.frame_ref in {frame.name for frame in document.frames} and mapping.pdu_ref in pdu_names:
            mappings_by_frame.setdefault(mapping.frame_ref, []).append(mapping)
    for frame in document.frames:
        bus_name = frame.bus_name
        if bus_name is None or bus_name not in can_frames and bus_name not in lin_frames:
            continue
        mappings = mappings_by_frame.get(frame.name, [])
        if frame.frame_id is None or frame.length is None or not mappings:
            document.diagnostics.append(
                ARXMLDiagnostic("warning", f"Frame '{frame.name}' lacks explicit bus, identifier, length, or PDU placement", frame.source)
            )
            continue
        placement = [PDUInstance(pdu_ref=mapping.pdu_ref, bit_position=mapping.bit_position) for mapping in mappings]
        id_format = _normalize_id_format(frame.id_format)
        if frame.kind in {"can", "can_fd"}:
            if id_format is None or bus_name not in can_frames:
                document.diagnostics.append(
                    ARXMLDiagnostic("warning", f"Frame '{frame.name}' lacks an explicit CAN identifier format", frame.source)
                )
                continue
            if frame.kind == "can_fd":
                bus = next(bus for bus in document.buses if bus.name == bus_name)
                if bus.fd_baud_rate is None:
                    document.diagnostics.append(
                        ARXMLDiagnostic("warning", f"CAN-FD frame '{frame.name}' lacks an explicit CAN-FD data rate", frame.source)
                    )
                    continue
                can_frames[bus_name].append(
                    CANFDFrame(
                        name=frame.name,
                        length=frame.length,
                        can_id=frame.frame_id,
                        id_format=cast(Literal["standard_11bit", "extended_29bit"], id_format),
                        packed_pdus=placement,
                        bit_rate_switch=frame.bit_rate_switch if frame.bit_rate_switch is not None else True,
                        error_state_indicator=frame.error_state_indicator if frame.error_state_indicator is not None else False,
                        type="can_fd",
                    )
                )
            else:
                can_frames[bus_name].append(
                    CANFrame(
                        name=frame.name,
                        length=frame.length,
                        can_id=frame.frame_id,
                        id_format=cast(Literal["standard_11bit", "extended_29bit"], id_format),
                        packed_pdus=placement,
                        type="can",
                    )
                )
        else:
            if bus_name not in lin_frames:
                continue
            checksum_type = _normalize_checksum_type(frame.checksum_type)
            if frame.checksum_type is not None and checksum_type is None:
                document.diagnostics.append(ARXMLDiagnostic("warning", f"LIN frame '{frame.name}' has unsupported checksum type", frame.source))
                continue
            lin_frames[bus_name].append(
                LINFrame(
                    name=frame.name,
                    length=frame.length,
                    lin_id=frame.frame_id,
                    packed_pdus=placement,
                    checksum_type=cast(Literal["classic", "enhanced"], checksum_type or "enhanced"),
                    type="lin",
                )
            )

    payload = {
        "ecus": ecus,
        "metadata": {
            "type": "system",
            "author": "ARXML importer",
            "compatible_flync_version": {"version": "0.0.0"},
            "release": {"version": "0.0.0"},
        },
    }
    can_buses = [
        {
            "name": bus.name,
            "baud_rate": bus.baud_rate,
            "fd_enabled": bus.fd_baud_rate is not None,
            "fd_baud_rate": bus.fd_baud_rate,
            "frames": can_frames[bus.name],
        }
        for bus in document.buses
        if bus.kind == "can" and bus.baud_rate is not None
    ]
    channels_payload: dict[str, object] = {"pdus": pdus}
    if can_buses:
        channels_payload["can_buses"] = can_buses
    lin_buses = [
        {"name": bus.name, "baud_rate": bus.baud_rate, "lin_protocol_version": "2.1", "lin_language_version": "2.1", "frames": lin_frames[bus.name]}
        for bus in document.buses
        if bus.kind == "lin" and bus.baud_rate is not None
    ]
    if lin_buses:
        channels_payload["lin_buses"] = lin_buses
    if can_buses or lin_buses or pdus:
        payload["communication"] = {"channels": channels_payload}
    someip_services = [service for item in document.someip_services if (service := _someip_service_payload(item, document)) is not None]
    diagnostics_payload = _diagnostics_payload(document)
    if someip_services or diagnostics_payload:
        communication = cast(dict[str, object], payload.setdefault("communication", {}))
        if someip_services:
            communication["someip_config"] = {**_someip_timing_config(), "services": someip_services}
        if diagnostics_payload:
            communication["diagnostics_config"] = diagnostics_payload
    return FLYNCModel.model_validate(payload)


def _normalize_id_format(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper().replace("-", "_")
    if normalized in {"STANDARD", "STANDARD_11BIT", "11BIT"}:
        return "standard_11bit"
    if normalized in {"EXTENDED", "EXTENDED_29BIT", "29BIT"}:
        return "extended_29bit"
    return None


def _normalize_checksum_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    return normalized if normalized in {"classic", "enhanced"} else None


def _ethernet_interface_config(interface, document: ARXMLDocument) -> dict:
    """Map only explicit Layer 2/3 values from one owned physical channel."""
    if interface is None:
        return {}
    config: dict[str, object] = {}
    if interface.mac_address:
        config["mac_address"] = interface.mac_address
    virtual_interfaces: list[dict[str, object]] = []
    for virtual in interface.virtual_interfaces:
        addresses: list[dict[str, object]] = []
        for address, netmask in virtual.ipv4_addresses:
            addresses.append({"address": address, "ipv4netmask": netmask})
        for address, prefix in virtual.ipv6_addresses:
            addresses.append({"address": address, "ipv6prefix": prefix})
        virtual_interfaces.append({"name": virtual.name, "vlanid": virtual.vlan_id, "addresses": addresses})
    if virtual_interfaces:
        config["virtual_interfaces"] = virtual_interfaces
    return config


def _ethernet_socket_containers(interface, document: ARXMLDocument) -> list[dict[str, object]]:
    """Create socket containers only for complete, explicitly addressed socket records."""
    if interface is None:
        return []
    containers: list[dict[str, object]] = []
    for virtual in interface.virtual_interfaces:
        addresses = [address for address, _ in virtual.ipv4_addresses] + [address for address, _ in virtual.ipv6_addresses]
        sockets: list[object] = []
        for socket in virtual.sockets:
            address = socket.address or (addresses[0] if len(addresses) == 1 else None)
            if address is None or socket.port is None:
                document.diagnostics.append(
                    ARXMLDiagnostic(
                        "warning",
                        f"Socket '{socket.name}' lacks an explicit, unambiguous endpoint address or port; socket was not emitted",
                        socket.source,
                    )
                )
                continue
            if socket.protocol == "udp":
                sockets.append(SocketUDP(name=socket.name, endpoint_address=address, port_no=socket.port))
            elif socket.protocol == "tcp" and socket.tcp_profile is not None:
                sockets.append(SocketTCP(name=socket.name, endpoint_address=address, port_no=socket.port, tcp_profile=socket.tcp_profile))
            elif socket.protocol == "tcp":
                document.diagnostics.append(
                    ARXMLDiagnostic("warning", f"TCP socket '{socket.name}' has no explicit TCP profile; socket was not emitted", socket.source)
                )
        if sockets:
            containers.append({"name": virtual.name, "vlan_id": virtual.vlan_id, "sockets": sockets})
    return containers


def _to_flync_signal(
    signal: ARXMLSignal, data_types: dict[str, ARXMLBaseDataType], compu_methods: dict[str, ARXMLCompuMethod], document: ARXMLDocument
) -> FLYNCSignal | None:
    """Map a signal only when its base type and linear conversion are explicit."""
    if signal.length is None or signal.data_type_ref not in data_types:
        document.diagnostics.append(ARXMLDiagnostic("warning", f"Signal '{signal.name}' has no resolvable AUTOSAR base data type", signal.source))
        return None
    bit_length = signal.length
    data_type = data_types[signal.data_type_ref]
    encoding = (data_type.encoding or "").upper()
    if "IEEE" in encoding or "REAL" in encoding or "FLOAT" in encoding:
        signal_type = SignalDataType.FLOAT32 if bit_length <= 32 else SignalDataType.FLOAT64
    elif "UNSIGNED" in encoding or encoding in {"UINT", "INTEGER"}:
        signal_type = next(
            (
                value
                for value in (SignalDataType.UINT8, SignalDataType.UINT16, SignalDataType.UINT32, SignalDataType.UINT64)
                if (natural_width := value.natural_bit_width()) is not None and bit_length <= natural_width
            ),
            SignalDataType.BYTEARRAY,
        )
    elif "SIGNED" in encoding or encoding in {"SINT", "INT"}:
        signal_type = next(
            (
                value
                for value in (SignalDataType.INT8, SignalDataType.INT16, SignalDataType.INT32, SignalDataType.INT64)
                if (natural_width := value.natural_bit_width()) is not None and bit_length <= natural_width
            ),
            SignalDataType.BYTEARRAY,
        )
    else:
        document.diagnostics.append(
            ARXMLDiagnostic("warning", f"Signal '{signal.name}' uses unsupported base type encoding '{data_type.encoding}'", data_type.source)
        )
        return None
    compu = compu_methods.get(signal.compu_method_ref) if signal.compu_method_ref else None
    if compu is None or compu.factor is None or compu.offset is None:
        document.diagnostics.append(
            ARXMLDiagnostic(
                "warning", f"Signal '{signal.name}' has no resolved linear COMPU-METHOD; identity scaling was not assumed", signal.source
            )
        )
        return None
    return FLYNCSignal(
        name=signal.name,
        bit_length=bit_length,
        data_type=signal_type,
        factor=compu.factor if compu else 1.0,
        offset=compu.offset if compu else 0.0,
        unit=signal.unit or (compu.unit if compu else None),
        lower_limit=signal.lower_limit if signal.lower_limit is not None else (compu.lower_limit if compu else None),
        upper_limit=signal.upper_limit if signal.upper_limit is not None else (compu.upper_limit if compu else None),
    )


class ARXMLConverter(BaseConverter):
    """Convert a single ARXML file or directory of ARXML files to FLYNC."""

    name = "arxml"

    def can_decode(self) -> bool:
        """Return whether the configured path is an ARXML file or directory."""
        if self.config is None:
            return False
        path = Path(self.config.config_path)
        return path.is_dir() or path.suffix.lower() == ".arxml"

    def encode(self, source: FLYNCModel):
        """Write a FLYNC model to the configured workspace directory."""
        if self.config is None:
            raise ValueError("config must be set before encoding")
        dump_flync_workspace(source, self.config.config_path, "ARXML converted workspace")

    def decode(self) -> FLYNCModel:
        """Decode configured ARXML input into a validated FLYNC model."""
        if self.config is None:
            raise ValueError("config must be set before decoding")
        document = load_arxml_documents(self.config.config_path)
        logger.info("Parsed %d ECU instances from ARXML input", len(document.ecus))
        return _model_from_documents(document)


@hookimpl
def register_converters():
    """Register the ARXML converter with the Pluggy registry."""
    return [ARXMLConverter()]
