"""Generate PlantUML, SVG, and HTML topology outputs from an ARXML folder."""

from __future__ import annotations

import argparse
import logging
import zipfile
from pathlib import Path
from typing import Callable

from flync.sdk.helpers.generation_helpers import dump_flync_workspace
from flync_cli.commands.generate_system_uml import parse_and_generate_uml
from flync_cli.convert_puml import convert_puml
from flync_converter.base import ConverterConfig
from flync_converter.converters.arxml_converter import ARXMLConverter

logger = logging.getLogger(__name__)


def _append_communication_annotations(uml_lines: list[str], model) -> None:
    """Add compact L3/SOME-IP/diagnostic facts to the architecture diagram."""
    communication = model.communication
    if communication is None:
        return
    lines = ["' Communication summary", "legend right", "  == Communication summary =="]
    services = getattr(getattr(communication, "someip_config", None), "services", []) or []
    if services:
        lines.append(f"  SOME/IP services: {len(services)}")
        for service in services[:12]:
            lines.append(f"  - {service.name} (0x{service.id:04X}, v{service.major_version}.{service.minor_version})")
        if len(services) > 12:
            lines.append(f"  - ... {len(services) - 12} more")
    channels = getattr(communication, "channels", None)
    if channels is not None:
        can_buses = getattr(channels, "can_buses", None) or []
        lin_buses = getattr(channels, "lin_buses", None) or []
        if can_buses:
            lines.append(f"  CAN buses: {len(can_buses)}")
        if lin_buses:
            lines.append(f"  LIN buses: {len(lin_buses)}")
        pdus = getattr(channels, "pdus", None) or []
        if pdus:
            lines.append(f"  PDUs: {len(pdus)}")
    diagnostics = getattr(communication, "diagnostics_config", None)
    if diagnostics is not None:
        uds = getattr(diagnostics, "uds", None)
        dids = getattr(uds, "dids", None) if uds is not None else None
        dtcs = getattr(uds, "dtcs", None) if uds is not None else None
        if dids:
            lines.append(f"  DIDs: {len(dids)}")
        if dtcs:
            lines.append(f"  DTCs: {len(dtcs)}")
    if len(lines) > 3:
        lines.extend(["  ==", "endlegend", ""])
        uml_lines[1:1] = lines


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="Convert an ARXML file/folder to topology.puml, topology.svg, and topology.html.")
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Folder containing ARXML files, including nested files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("arxml-topology-output"),
        help="Output folder for topology.puml, topology.svg, and topology.html.",
    )
    return parser


def generate_topology(input_folder: Path, output_folder: Path, progress: Callable[[str], None] | None = None) -> tuple[Path, Path, Path, Path]:
    """Convert ARXML input and render the current FLYNC topology snapshot."""
    report = progress or logger.info
    files = sorted(input_folder.rglob("*.arxml"))
    report(f"Discovered {len(files)} ARXML file(s).")
    converter = ARXMLConverter(ConverterConfig(config_path=str(input_folder)))
    report("Parsing ARXML and validating the FLYNC model...")
    model = converter.decode()
    report(f"Validated {len(model.ecus)} ECU model(s).")
    output_folder.mkdir(parents=True, exist_ok=True)

    puml_path = output_folder / "topology.puml"
    svg_path = output_folder / "topology.svg"
    html_path = output_folder / "topology.html"
    config_folder = output_folder / "flync_config"
    config_zip = output_folder / "flync_config.zip"

    report("Writing generated FLYNC workspace configuration...")
    dump_flync_workspace(model, str(config_folder), "ARXML converted workspace")
    with zipfile.ZipFile(config_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(config_folder.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(config_folder))

    uml_lines, included_ecus = parse_and_generate_uml(model, None, ["iface"], model.ecus, [])
    if not included_ecus:
        raise ValueError("The converted model contains no Ethernet components to draw")
    _append_communication_annotations(uml_lines, model)
    report("Writing PlantUML topology source...")
    puml_path.write_text("\n".join(uml_lines), encoding="utf-8")

    report("Rendering SVG and HTML with PlantUML; this may take a moment...")
    if not convert_puml(str(puml_path), "html"):
        raise RuntimeError("PlantUML rendering failed; check that Java is installed and on PATH")
    if not svg_path.exists() or not html_path.exists():
        raise RuntimeError("PlantUML did not create both topology.svg and topology.html")
    report("Diagram artifacts are ready.")
    return puml_path, svg_path, html_path, config_zip


def main() -> int:
    """Run the ARXML topology export command."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args()
    if not args.input_folder.exists():
        raise SystemExit(f"Input path does not exist: {args.input_folder}")
    if not args.input_folder.is_dir():
        raise SystemExit(f"Input path must be a folder: {args.input_folder}")

    try:
        puml_path, svg_path, html_path, config_zip = generate_topology(args.input_folder, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Generated: {puml_path}")
    print(f"Generated: {svg_path}")
    print(f"Generated: {html_path}")
    print(f"Generated: {config_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
