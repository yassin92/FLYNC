from pathlib import Path

import pytest

from flync_converter.base import ConverterConfig
from flync_converter.converters.arxml_converter import ARXMLConverter, discover_arxml_files, load_arxml_documents

ARXML = """\
<AUTOSAR xmlns=\"http://autosar.org/schema/r4.0\">
  <AR-PACKAGES><AR-PACKAGE><ELEMENTS>
    <ECU-INSTANCE>
      <SHORT-NAME>ECU_A</SHORT-NAME>
      <COMM-CONTROLLER><SHORT-NAME>CTRL_A</SHORT-NAME>
        <ETHERNET-PHYSICAL-CHANNEL><SHORT-NAME>ETH_A</SHORT-NAME></ETHERNET-PHYSICAL-CHANNEL>
      </COMM-CONTROLLER>
    </ECU-INSTANCE>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES>
</AUTOSAR>
"""


def test_decode_maps_one_ecu_controller_and_interface(tmp_path: Path):
    source = tmp_path / "ecu.arxml"
    source.write_text(ARXML, encoding="utf-8")

    converter = ARXMLConverter(ConverterConfig(config_path=str(source)))
    model = converter.decode()

    assert converter.can_decode()
    assert [ecu.name for ecu in model.ecus] == ["ECU_A"]
    assert model.ecus[0].controllers[0].name == "CTRL_A"
    assert model.ecus[0].controllers[0].ethernet_interfaces[0].name == "ETH_A"


def test_decode_merges_sorted_directory_and_ecu_fragments(tmp_path: Path):
    first = tmp_path / "b.arxml"
    second = tmp_path / "a.arxml"
    first.write_text(ARXML.replace("ECU_A", "ECU_B").replace("CTRL_A", "CTRL_B").replace("ETH_A", "ETH_B"), encoding="utf-8")
    second.write_text(ARXML, encoding="utf-8")

    converter = ARXMLConverter(ConverterConfig(config_path=str(tmp_path)))
    assert [ecu.name for ecu in converter.decode().ecus] == ["ECU_A", "ECU_B"]

    duplicate = tmp_path / "duplicate.arxml"
    duplicate.write_text(ARXML.replace("ETH_A", "ETH_A_2"), encoding="utf-8")
    merged = converter.decode().ecus[0]
    assert [interface.name for interface in merged.controllers[0].ethernet_interfaces] == ["ETH_A", "ETH_A_2"]


def test_discover_rejects_empty_directory(tmp_path: Path):
    with pytest.raises(ValueError, match="No \\.arxml files"):
        discover_arxml_files(tmp_path)


def test_decode_reports_malformed_xml(tmp_path: Path):
    source = tmp_path / "broken.arxml"
    source.write_text("<AUTOSAR>", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid ARXML XML"):
        ARXMLConverter(ConverterConfig(config_path=str(source))).decode()


def test_arxml_converter_is_registered():
    from flync_converter.registry import registry

    registry.load_plugins()
    assert "arxml" in registry


def test_normalized_document_preserves_namespace_and_controller_ownership(tmp_path: Path):
    source = tmp_path / "owned.arxml"
    source.write_text(ARXML, encoding="utf-8")

    document = load_arxml_documents(source)

    assert document.namespaces == ("http://autosar.org/schema/r4.0",)
    assert document.ecus[0].controllers[0].name == "CTRL_A"
    assert document.ecus[0].controllers[0].interfaces == ("ETH_A",)
    assert document.ecus[0].source is not None
    assert document.ecus[0].source.file == str(source)


def test_conflicting_controller_kind_is_reported(tmp_path: Path):
    first = tmp_path / "first.arxml"
    second = tmp_path / "second.arxml"
    first.write_text(ARXML, encoding="utf-8")
    second.write_text(ARXML.replace("ETHERNET-PHYSICAL-CHANNEL", "CAN-CHANNEL"), encoding="utf-8")

    with pytest.raises(ValueError, match="Conflicting controller definition"):
        load_arxml_documents(tmp_path)


def test_document_extracts_can_bus_and_reports_unsupported_scope(tmp_path: Path):
    source = tmp_path / "communication.arxml"
    communication_xml = (
        "<CAN-CLUSTER><SHORT-NAME>BodyCan</SHORT-NAME><CAN-BAUDRATE>500000</CAN-BAUDRATE></CAN-CLUSTER>"
        "<SOMEIP-SERVICE-INTERFACE><SHORT-NAME>DemoService</SHORT-NAME></SOMEIP-SERVICE-INTERFACE></AUTOSAR>"
    )
    source.write_text(
        ARXML.replace("</AUTOSAR>", communication_xml),
        encoding="utf-8",
    )

    document = load_arxml_documents(source)

    assert [(bus.kind, bus.name, bus.baud_rate) for bus in document.buses] == [("can", "BodyCan", 500000)]
    assert any("lacks explicit service ID or version" in diagnostic.message for diagnostic in document.diagnostics)


def test_decode_emits_explicit_someip_service_metadata(tmp_path: Path):
    source = tmp_path / "someip.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<SOMEIP-SERVICE-INTERFACE><SHORT-NAME>DemoService</SHORT-NAME><SERVICE-ID>4660</SERVICE-ID>"
        "<MAJOR-VERSION>1</MAJOR-VERSION><MINOR-VERSION>2</MINOR-VERSION>"
        "<METHOD><SHORT-NAME>Read</SHORT-NAME><METHOD-ID>1</METHOD-ID></METHOD>"
        "<EVENT><SHORT-NAME>Status</SHORT-NAME><EVENT-ID>2</EVENT-ID></EVENT>"
        "<FIELD><SHORT-NAME>Mode</SHORT-NAME><FIELD-ID>3</FIELD-ID></FIELD>"
        "<EVENT-GROUP><SHORT-NAME>StatusGroup</SHORT-NAME><EVENTGROUP-ID>4</EVENTGROUP-ID>"
        "<EVENT-REF>/Status</EVENT-REF><FIELD-REF>/Mode</FIELD-REF></EVENT-GROUP>"
        "</SOMEIP-SERVICE-INTERFACE><ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    service = model.communication.someip_config.services[0]
    assert (service.id, service.major_version, service.minor_version) == (4660, 1, 2)
    assert [(method.name, method.id) for method in service.methods] == [("Read", 1)]
    assert [(event.name, event.id) for event in service.events] == [("Status", 2)]
    assert [(field.name, field.notifier_id) for field in service.fields] == [("Mode", 3)]
    assert [(group.name, group.id) for group in service.eventgroups] == [("StatusGroup", 4)]


def test_decode_keeps_incomplete_someip_members_as_diagnostics(tmp_path: Path):
    source = tmp_path / "someip_incomplete.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<SOMEIP-SERVICE-INTERFACE><SHORT-NAME>DemoService</SHORT-NAME><SERVICE-ID>4660</SERVICE-ID>"
        "<MAJOR-VERSION>1</MAJOR-VERSION><MINOR-VERSION>2</MINOR-VERSION>"
        "<EVENT><SHORT-NAME>MissingId</SHORT-NAME></EVENT>"
        "<EVENT-GROUP><SHORT-NAME>MissingMember</SHORT-NAME><EVENTGROUP-ID>4</EVENTGROUP-ID><EVENT-REF>/Unknown</EVENT-REF></EVENT-GROUP>"
        "</SOMEIP-SERVICE-INTERFACE><ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    document = load_arxml_documents(source)
    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    assert model.communication.someip_config.services[0].events == []
    assert model.communication.someip_config.services[0].eventgroups == []
    assert any("lacks a valid explicit identifier" in diagnostic.message for diagnostic in document.diagnostics)
    assert any("unknown member" in diagnostic.message for diagnostic in document.diagnostics)


def test_decode_emits_safe_did_and_dtc_inventory(tmp_path: Path):
    source = tmp_path / "diagnostics.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<DATA-IDENTIFIER><SHORT-NAME>VehicleId</SHORT-NAME><DID>61840</DID><BYTE-LENGTH>17</BYTE-LENGTH></DATA-IDENTIFIER>"
        "<DIAGNOSTIC-TROUBLE-CODE><SHORT-NAME>EngineFault</SHORT-NAME><DTC>66051</DTC></DIAGNOSTIC-TROUBLE-CODE>"
        "<DOIP-ENTITY><SHORT-NAME>DiagEntity</SHORT-NAME><LOGICAL-ADDRESS>3584</LOGICAL-ADDRESS></DOIP-ENTITY>"
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    diagnostics = model.communication.diagnostics_config
    assert diagnostics.uds.dids[0].did == 61840
    assert diagnostics.uds.dids[0].read_data.byte_length == 17
    assert diagnostics.uds.dtcs[0].dtc == 66051
    inventory = load_arxml_documents(source).diagnostics_inventory
    assert [(item.kind, item.identifier) for item in inventory] == [("did", 61840), ("doip", 3584), ("dtc", 66051)]


def test_decode_does_not_emit_did_without_explicit_payload_length(tmp_path: Path):
    source = tmp_path / "incomplete_diagnostics.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<DATA-IDENTIFIER><SHORT-NAME>VehicleId</SHORT-NAME><DID>61840</DID></DATA-IDENTIFIER>"
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    document = load_arxml_documents(source)
    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    assert model.communication is None
    assert any("incomplete payload" in diagnostic.message for diagnostic in document.diagnostics)


def test_document_extracts_pdu_signal_and_placement(tmp_path: Path):
    source = tmp_path / "pdu.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<I-SIGNAL><SHORT-NAME>Speed</SHORT-NAME><LENGTH>16</LENGTH></I-SIGNAL>"
        "<I-SIGNAL-I-PDU><SHORT-NAME>BodyPdu</SHORT-NAME><LENGTH>8</LENGTH>"
        "<I-SIGNAL-TO-I-PDU-MAPPINGS><I-SIGNAL-TO-I-PDU-MAPPING>"
        "<I-SIGNAL-REF>/Speed</I-SIGNAL-REF><START-POSITION>8</START-POSITION>"
        "<PACKING-BYTE-ORDER>LE</PACKING-BYTE-ORDER>"
        "</I-SIGNAL-TO-I-PDU-MAPPING></I-SIGNAL-TO-I-PDU-MAPPINGS>"
        "</I-SIGNAL-I-PDU>"
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE>"
        "</AUTOSAR>",
        encoding="utf-8",
    )

    document = load_arxml_documents(source)

    assert document.signals[0].name == "Speed"
    assert document.signals[0].length == 16
    assert document.pdus[0].name == "BodyPdu"
    assert document.pdus[0].signal_refs == ("Speed",)
    assert document.pdus[0].placements == (("Speed", 8, "LE"),)


def test_decode_emits_typed_pdu_and_explicit_can_frame(tmp_path: Path):
    source = tmp_path / "typed_can.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<CAN-CLUSTER><SHORT-NAME>BodyCan</SHORT-NAME><CAN-BAUDRATE>500000</CAN-BAUDRATE></CAN-CLUSTER>"
        "<SW-BASE-TYPE><SHORT-NAME>UInt16</SHORT-NAME><SIZE>16</SIZE><ENCODING>UNSIGNED</ENCODING></SW-BASE-TYPE>"
        "<COMPU-METHOD><SHORT-NAME>SpeedConversion</SHORT-NAME><COMPU-RATIONAL-COEFFS>"
        "<COMPU-NUMERATOR><V>0</V><V>0.1</V></COMPU-NUMERATOR><COMPU-DENOMINATOR><V>1</V></COMPU-DENOMINATOR>"
        "<UNIT-REF>/km_per_h</UNIT-REF></COMPU-RATIONAL-COEFFS></COMPU-METHOD>"
        "<I-SIGNAL><SHORT-NAME>Speed</SHORT-NAME><LENGTH>16</LENGTH><BASE-TYPE-REF>/UInt16</BASE-TYPE-REF>"
        "<COMPU-METHOD-REF>/SpeedConversion</COMPU-METHOD-REF><LOWER-LIMIT>0</LOWER-LIMIT><UPPER-LIMIT>250</UPPER-LIMIT></I-SIGNAL>"
        "<I-SIGNAL-I-PDU><SHORT-NAME>BodyPdu</SHORT-NAME><LENGTH>16</LENGTH><I-SIGNAL-TO-I-PDU-MAPPING>"
        "<I-SIGNAL-REF>/Speed</I-SIGNAL-REF><START-POSITION>0</START-POSITION><PACKING-BYTE-ORDER>LE</PACKING-BYTE-ORDER>"
        "</I-SIGNAL-TO-I-PDU-MAPPING></I-SIGNAL-I-PDU>"
        "<CAN-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyCan</BUS-REF><CAN-ID>291</CAN-ID><ID-FORMAT>standard_11bit</ID-FORMAT>"
        "<LENGTH>2</LENGTH><PDU-REF>/BodyPdu</PDU-REF></CAN-FRAME>"
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    pdu = model.communication.channels.pdus[0]
    signal = pdu.signals[0].signal
    frame = model.communication.channels.can_buses[0].frames[0]
    assert signal.data_type.value == "uint16"
    assert signal.factor == 0.1
    assert signal.offset == 0
    assert signal.unit == "km_per_h"
    assert signal.lower_limit == 0
    assert signal.upper_limit == 250
    assert frame.name == "BodyFrame"
    assert frame.can_id == 291
    assert frame.packed_pdus[0].pdu_ref == "BodyPdu"


def _mapped_signal_xml(frame: str, mapping: str, bus: str = "CAN-CLUSTER", bus_fields: str = "<CAN-BAUDRATE>500000</CAN-BAUDRATE>") -> str:
    return (
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        f"<{bus}><SHORT-NAME>BodyBus</SHORT-NAME>{bus_fields}</{bus}>"
        "<SW-BASE-TYPE><SHORT-NAME>UInt16</SHORT-NAME><SIZE>16</SIZE><ENCODING>UNSIGNED</ENCODING></SW-BASE-TYPE>"
        "<COMPU-METHOD><SHORT-NAME>Identity</SHORT-NAME><COMPU-RATIONAL-COEFFS>"
        "<COMPU-NUMERATOR><V>0</V><V>1</V></COMPU-NUMERATOR><COMPU-DENOMINATOR><V>1</V></COMPU-DENOMINATOR>"
        "</COMPU-RATIONAL-COEFFS></COMPU-METHOD>"
        "<I-SIGNAL><SHORT-NAME>Value</SHORT-NAME><LENGTH>16</LENGTH><BASE-TYPE-REF>/UInt16</BASE-TYPE-REF>"
        "<COMPU-METHOD-REF>/Identity</COMPU-METHOD-REF></I-SIGNAL>"
        "<I-SIGNAL-I-PDU><SHORT-NAME>BodyPdu</SHORT-NAME><LENGTH>16</LENGTH><I-SIGNAL-TO-I-PDU-MAPPING>"
        "<I-SIGNAL-REF>/Value</I-SIGNAL-REF><START-POSITION>0</START-POSITION><PACKING-BYTE-ORDER>LE</PACKING-BYTE-ORDER>"
        "</I-SIGNAL-TO-I-PDU-MAPPING></I-SIGNAL-I-PDU>"
        f"{frame}{mapping}<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>"
    )


def test_decode_resolves_pdu_to_frame_mapping_and_preserves_offset(tmp_path: Path):
    source = tmp_path / "mapped.arxml"
    source.write_text(
        _mapped_signal_xml(
            "<CAN-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyBus</BUS-REF><CAN-ID>291</CAN-ID>"
            "<ID-FORMAT>STANDARD</ID-FORMAT><LENGTH>4</LENGTH></CAN-FRAME>",
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>8</START-POSITION></PDU-TO-FRAME-MAPPING>",
        ),
        encoding="utf-8",
    )

    document = load_arxml_documents(source)
    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    assert document.pdu_frame_mappings[0].bit_position == 8
    assert model.communication.channels.can_buses[0].frames[0].packed_pdus[0].bit_position == 8


@pytest.mark.parametrize(
    ("mapping", "expected"),
    [
        (
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/Missing</PDU-REF>"
            "<START-POSITION>0</START-POSITION></PDU-TO-FRAME-MAPPING>",
            "unresolved PDU",
        ),
        (
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>0</START-POSITION></PDU-TO-FRAME-MAPPING>" * 2,
            "Duplicate PDU-to-frame mapping",
        ),
        (
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>" "</PDU-TO-FRAME-MAPPING>",
            "Incomplete PDU-to-frame mapping",
        ),
    ],
)
def test_mapping_rejects_unresolved_duplicate_or_incomplete_input(tmp_path: Path, mapping: str, expected: str):
    source = tmp_path / "invalid_mapping.arxml"
    source.write_text(
        _mapped_signal_xml(
            "<CAN-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyBus</BUS-REF><CAN-ID>291</CAN-ID>"
            "<ID-FORMAT>STANDARD</ID-FORMAT><LENGTH>4</LENGTH></CAN-FRAME>",
            mapping,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=expected):
        load_arxml_documents(source)


def test_mapping_rejects_overlapping_pdu_placements(tmp_path: Path):
    source = tmp_path / "overlap.arxml"
    source.write_text(
        _mapped_signal_xml(
            "<CAN-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyBus</BUS-REF><CAN-ID>291</CAN-ID>"
            "<ID-FORMAT>STANDARD</ID-FORMAT><LENGTH>4</LENGTH></CAN-FRAME>",
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>0</START-POSITION></PDU-TO-FRAME-MAPPING>"
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>8</START-POSITION></PDU-TO-FRAME-MAPPING>",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="PDU placement overlap"):
        load_arxml_documents(source)


def test_decode_emits_explicit_can_fd_fields(tmp_path: Path):
    source = tmp_path / "can_fd.arxml"
    source.write_text(
        _mapped_signal_xml(
            "<CAN-FD-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyBus</BUS-REF><CAN-ID>291</CAN-ID>"
            "<ID-FORMAT>STANDARD</ID-FORMAT><LENGTH>12</LENGTH><BIT-RATE-SWITCH>false</BIT-RATE-SWITCH>"
            "<ERROR-STATE-INDICATOR>true</ERROR-STATE-INDICATOR></CAN-FD-FRAME>",
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>0</START-POSITION></PDU-TO-FRAME-MAPPING>",
            bus_fields="<CAN-BAUDRATE>500000</CAN-BAUDRATE><CAN-FD-BAUDRATE>2000000</CAN-FD-BAUDRATE>",
        ),
        encoding="utf-8",
    )

    frame = ARXMLConverter(ConverterConfig(config_path=str(source))).decode().communication.channels.can_buses[0].frames[0]

    assert frame.type == "can_fd"
    assert frame.bit_rate_switch is False
    assert frame.error_state_indicator is True


def test_decode_emits_explicit_lin_checksum(tmp_path: Path):
    source = tmp_path / "lin.arxml"
    source.write_text(
        _mapped_signal_xml(
            "<LIN-FRAME><SHORT-NAME>BodyFrame</SHORT-NAME><BUS-REF>/BodyBus</BUS-REF><LIN-ID>18</LIN-ID>"
            "<LENGTH>4</LENGTH><CHECKSUM-TYPE>classic</CHECKSUM-TYPE></LIN-FRAME>",
            "<PDU-TO-FRAME-MAPPING><FRAME-REF>/BodyFrame</FRAME-REF><PDU-REF>/BodyPdu</PDU-REF>"
            "<START-POSITION>0</START-POSITION></PDU-TO-FRAME-MAPPING>",
            bus="LIN-CLUSTER",
            bus_fields="<LIN-SPEED>19200</LIN-SPEED>",
        ),
        encoding="utf-8",
    )

    frame = ARXMLConverter(ConverterConfig(config_path=str(source))).decode().communication.channels.lin_buses[0].frames[0]

    assert frame.lin_id == 18
    assert frame.checksum_type == "classic"


def test_decode_maps_owned_ethernet_vlan_ip_and_udp_tcp_sockets(tmp_path: Path):
    source = tmp_path / "ethernet_l23.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME>"
        "<COMM-CONTROLLER><SHORT-NAME>CTRL_A</SHORT-NAME>"
        "<ETHERNET-PHYSICAL-CHANNEL><SHORT-NAME>ETH_A</SHORT-NAME><MAC-ADDRESS>02:00:00:00:00:01</MAC-ADDRESS>"
        "<VLAN><SHORT-NAME>VLAN_A</SHORT-NAME><VLAN-ID>42</VLAN-ID>"
        "<IPV-4-EXT><IPV-4-ADDRESS>192.0.2.10</IPV-4-ADDRESS><IPV-4-SUBNET-MASK>255.255.255.0</IPV-4-SUBNET-MASK>"
        "<UDP-SOCKET><SHORT-NAME>Udp_A</SHORT-NAME><PORT-NUMBER>30490</PORT-NUMBER></UDP-SOCKET></IPV-4-EXT>"
        "<IPV-6-EXT><IPV-6-ADDRESS>2001:db8::10</IPV-6-ADDRESS><IPV-6-PREFIX-LENGTH>64</IPV-6-PREFIX-LENGTH>"
        "<TCP-SOCKET><SHORT-NAME>Tcp_A</SHORT-NAME><PORT-NUMBER>30491</PORT-NUMBER><TCP-PROFILE-ID>7</TCP-PROFILE-ID></TCP-SOCKET></IPV-6-EXT>"
        "</VLAN></ETHERNET-PHYSICAL-CHANNEL></COMM-CONTROLLER></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()
    controller = model.ecus[0].controllers[0]
    interface = controller.ethernet_interfaces[0]
    config = interface.interface_config

    assert controller.name == "CTRL_A"
    assert interface.name == "ETH_A"
    assert str(config.mac_address) == "02:00:00:00:00:01"
    assert config.virtual_interfaces[0].vlanid == 42
    assert {str(address.address) for address in config.virtual_interfaces[0].addresses} == {"192.0.2.10", "2001:db8::10"}
    sockets = interface.sockets[0].sockets
    assert [(socket.protocol, socket.port_no) for socket in sockets] == [("udp", 30490), ("tcp", 30491)]
    assert sockets[1].tcp_profile == 7


def test_decode_does_not_invent_incomplete_tcp_socket(tmp_path: Path):
    source = tmp_path / "incomplete_socket.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME><COMM-CONTROLLER><SHORT-NAME>CTRL_A</SHORT-NAME>"
        "<ETHERNET-PHYSICAL-CHANNEL><SHORT-NAME>ETH_A</SHORT-NAME><VLAN><SHORT-NAME>VLAN_A</SHORT-NAME><VLAN-ID>42</VLAN-ID>"
        "<IPV-4-EXT><IPV-4-ADDRESS>192.0.2.10</IPV-4-ADDRESS><IPV-4-SUBNET-MASK>255.255.255.0</IPV-4-SUBNET-MASK>"
        "<TCP-SOCKET><SHORT-NAME>Tcp_A</SHORT-NAME><PORT-NUMBER>30491</PORT-NUMBER></TCP-SOCKET></IPV-4-EXT>"
        "</VLAN></ETHERNET-PHYSICAL-CHANNEL></COMM-CONTROLLER></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    document = load_arxml_documents(source)
    model = ARXMLConverter(ConverterConfig(config_path=str(source))).decode()

    assert any("no explicit TCP profile" in diagnostic.message for diagnostic in document.diagnostics)
    assert model.ecus[0].controllers[0].ethernet_interfaces[0].sockets == []


def test_unresolved_ethernet_topology_reference_is_diagnostic(tmp_path: Path):
    source = tmp_path / "unresolved_topology.arxml"
    source.write_text(
        '<AUTOSAR xmlns="http://autosar.org/schema/r4.0">'
        "<ETHERNET-TOPOLOGY-CONNECTION><SHORT-NAME>Link_A</SHORT-NAME>"
        "<PHYSICAL-CHANNEL-REF>/MissingChannel</PHYSICAL-CHANNEL-REF></ETHERNET-TOPOLOGY-CONNECTION>"
        "<ECU-INSTANCE><SHORT-NAME>ECU_A</SHORT-NAME></ECU-INSTANCE></AUTOSAR>",
        encoding="utf-8",
    )

    document = load_arxml_documents(source)

    assert any("unresolved endpoint" in diagnostic.message for diagnostic in document.diagnostics)
    assert any("topology was not emitted" in diagnostic.message for diagnostic in document.diagnostics)
