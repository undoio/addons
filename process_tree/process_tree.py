#!/usr/bin/env python3
"""
Process Tree Visualizer

Reads .undo recording files and generates a process tree visualization.
Shows both ASCII tree output and SVG timeline diagrams.

Can be used as a standalone script or as a GDB command.
"""

import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import argparse
import xml.etree.ElementTree as ET

try:
    import gdb

    HAS_GDB = True
except ImportError:
    HAS_GDB = False


def check_undo_available() -> None:
    """Check if 'undo' executable is available on PATH."""
    if not shutil.which("undo"):
        raise FileNotFoundError(
            "Error: 'undo' executable not found. "
            "Please ensure 'undo' is installed and available on your PATH."
        )


@dataclass
class ForkPosition:
    """Represents a fork point in the process tree layout."""

    fork_x: int
    child_pid: int
    child_start_x: int


@dataclass
class LayoutInfo:
    """Layout information for a process in the SVG visualization."""

    y: int
    line_start_x: int = 0
    fork_positions: List[ForkPosition] = field(default_factory=list)


@dataclass
class Process:
    """Represents a single process in the tree."""

    pid: int
    ppid: Optional[int]
    recording_file: str
    start_time: float = 0.0
    children: List["Process"] = field(default_factory=list)


class RecordingParser:
    """Handles extraction of process information from .undo recording files."""

    def extract_process_info(
        self, recording_file: Path
    ) -> Tuple[Optional[int], Optional[int], float]:
        """Extract PID, PPID, and start time from a .undo recording file."""
        try:
            # Get process info (PID/PPID)
            pid, ppid = self._get_process_ids(recording_file)
            if pid is None:
                return None, None, 0.0

            # Get timing info
            start_time = self._get_start_time(recording_file)

            return pid, ppid, start_time

        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error processing {recording_file}: {e}", file=sys.stderr)
            return None, None, 0.0

    def _run_recording_json(self, recording_file: Path, section: str) -> dict:
        """Run undo recording-json and return parsed JSON data."""
        cmd = ["undo", "recording-json", "-s", section, str(recording_file)]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def _get_process_ids(
        self, recording_file: Path
    ) -> Tuple[Optional[int], Optional[int]]:
        """Get PID and PPID from recording file."""
        data = self._run_recording_json(recording_file, "d")
        pid = data["debuggee"]["state_load_rchild_pid"]
        ppid = data["debuggee"]["rchild_ppid"]
        return pid, ppid

    def _get_start_time(self, recording_file: Path) -> float:
        """Get start time from recording file header."""
        data = self._run_recording_json(recording_file, "h")
        utc_start = data["header"]["utc_start"]
        utc_start_ns = data["header"]["utc_start_ns"]
        try:
            return float(utc_start) + float(utc_start_ns) / 1_000_000_000
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid timestamp data in recording header: {e}")


class ProcessTree:
    """Represents and manages a tree of processes."""

    def __init__(self):
        self.processes: Dict[int, Process] = {}
        self.root: Optional[Process] = None

    def add_process(self, process: Process) -> None:
        """Add a process to the tree."""
        self.processes[process.pid] = process

    def build_relationships(self) -> None:
        """Build parent-child relationships and find root process."""
        # Link children to parents
        for process in self.processes.values():
            if process.ppid is not None and process.ppid in self.processes:
                parent = self.processes[process.ppid]
                parent.children.append(process)

        # Find root process (one with no parent in our dataset)
        roots = [
            p
            for p in self.processes.values()
            if p.ppid is None or p.ppid not in self.processes
        ]

        if len(roots) != 1:
            print(
                f"Warning: Found {len(roots)} root processes, expected 1",
                file=sys.stderr,
            )
            if not roots:
                raise ValueError("No root process found - cannot build process tree")

        self.root = roots[0]
        self._sort_children_by_start_time()

    def _sort_children_by_start_time(self) -> None:
        """Sort all children by their start time (chronological order)."""
        for process in self.processes.values():
            process.children.sort(key=lambda p: p.start_time)


class ASCIIRenderer:
    """Renders process tree as ASCII art."""

    def render(self, tree: ProcessTree) -> None:
        """Generate ASCII art visualization of the process tree."""
        if not tree.root:
            print("No root process found")
            return

        print("\nProcess Tree Visualization:")
        print("=" * 50)
        self._render_process(tree.root, "", True)

    def _render_process(self, process: Process, prefix: str, is_last: bool) -> None:
        """Recursively render a process and its children."""
        # Print current process
        connector = "└── " if is_last else "├── "
        filename = Path(process.recording_file).name
        print(f"{prefix}{connector}PID {process.pid} ({filename})")

        # Update prefix for children
        child_prefix = prefix + ("    " if is_last else "│   ")

        # Print children
        for i, child in enumerate(process.children):
            is_child_last = i == len(process.children) - 1
            self._render_process(child, child_prefix, is_child_last)


class SVGRenderer:
    """Renders process tree as SVG timeline diagram."""

    def __init__(self):
        # Layout parameters
        self.line_height = 80
        self.line_length = 600
        self.line_start_x = 120
        self.margin_top = 50
        self.margin_bottom = 30
        self.fork_spacing = 100
        self.fork_offset = 150

    def render(self, tree: ProcessTree, output_file: str) -> None:
        """Generate SVG visualization of the process tree."""
        if not tree.root:
            print("No root process found")
            return

        layout = self._calculate_layout(tree)
        svg_width, svg_height = self._calculate_dimensions(layout)

        # Create SVG
        svg = self._create_svg_element(svg_width, svg_height)
        self._add_styles(svg)

        # Draw elements
        self._draw_process_lines(svg, tree.processes.values(), layout)
        self._draw_fork_connections(svg, tree.processes.values(), layout)

        # Save file
        self._save_svg(svg, output_file)

    def _calculate_layout(self, tree: ProcessTree) -> Dict[int, LayoutInfo]:
        """Calculate positions for all processes and their forks."""
        assert tree.root is not None, "tree.root must not be None"
        layout = {}

        # Calculate Y positions for each process
        y_positions = {}
        current_y = 0

        def assign_y_positions(process: Process):
            nonlocal current_y
            y_positions[process.pid] = current_y
            current_y += 1

            for child in process.children:
                assign_y_positions(child)

        assign_y_positions(tree.root)

        # Convert to layout structure
        for pid, y_index in y_positions.items():
            layout[pid] = LayoutInfo(y=self.margin_top + y_index * self.line_height)

        # Now calculate X positions recursively
        def calculate_x_positions(process: Process, current_x: int) -> None:
            layout[process.pid].line_start_x = current_x

            # Calculate fork positions for children
            if process.children:
                fork_base_x = current_x + self.fork_offset
                for i, child in enumerate(process.children):
                    fork_x = fork_base_x + i * self.fork_spacing
                    child_start_x = fork_x + 50

                    layout[process.pid].fork_positions.append(
                        ForkPosition(
                            fork_x=fork_x,
                            child_pid=child.pid,
                            child_start_x=child_start_x,
                        )
                    )

                    # Recursively calculate for child
                    calculate_x_positions(child, child_start_x)

        calculate_x_positions(tree.root, self.line_start_x)
        return layout

    def _calculate_dimensions(self, layout: Dict[int, LayoutInfo]) -> Tuple[int, int]:
        """Calculate required SVG dimensions."""
        max_x = max(info.line_start_x + self.line_length for info in layout.values())
        max_y = max(info.y for info in layout.values())

        width = max_x + 100
        height = max_y + self.margin_bottom + self.line_height
        return width, height

    def _create_svg_element(self, width: int, height: int) -> ET.Element:
        """Create the root SVG element with white background."""
        svg = ET.Element(
            "svg",
            width=str(width),
            height=str(height),
            xmlns="http://www.w3.org/2000/svg",
        )

        # Add white background
        ET.SubElement(svg, "rect", width=str(width), height=str(height), fill="white")
        return svg

    def _add_styles(self, svg: ET.Element) -> None:
        """Add CSS styles to the SVG."""
        style = ET.SubElement(svg, "style")
        style.text = """
            .process-line { stroke: black; stroke-width: 3; }
            .fork-line { stroke: black; stroke-width: 2; }
            .process-label { font-family: Arial, sans-serif; font-size: 14px; font-weight: bold; }
            .fork-label { font-family: Arial, sans-serif; font-size: 12px; }
            .filename-label { font-family: Arial, sans-serif; font-size: 10px; fill: #666; }
        """

    def _draw_process_lines(
        self, svg: ET.Element, processes: Iterable[Process], layout: Dict[int, LayoutInfo]
    ) -> None:
        """Draw horizontal timeline lines for each process."""
        for process in processes:
            info = layout[process.pid]
            y = info.y
            start_x = info.line_start_x
            end_x = start_x + self.line_length

            # Main timeline
            ET.SubElement(
                svg,
                "line",
                x1=str(start_x),
                y1=str(y),
                x2=str(end_x),
                y2=str(y),
                **{"class": "process-line"},
            )

            # PID label (above line)
            ET.SubElement(
                svg,
                "text",
                x=str(start_x - 90),
                y=str(y - 10),
                **{"class": "process-label"},
            ).text = f"PID {process.pid}"

            # Filename label (below line)
            filename = Path(process.recording_file).name
            ET.SubElement(
                svg,
                "text",
                x=str(start_x + 20),
                y=str(y + 20),
                **{"class": "filename-label"},
            ).text = filename

    def _draw_fork_connections(
        self, svg: ET.Element, processes: Iterable[Process], layout: Dict[int, LayoutInfo]
    ) -> None:
        """Draw fork connections between parent and child processes."""
        for process in processes:
            if not process.children:
                continue

            parent_info = layout[process.pid]
            parent_y = parent_info.y

            for fork_info in parent_info.fork_positions:
                fork_x = fork_info.fork_x
                child_pid = fork_info.child_pid
                child_start_x = fork_info.child_start_x
                child_y = layout[child_pid].y

                # Fork label
                ET.SubElement(
                    svg,
                    "text",
                    x=str(fork_x - 15),
                    y=str(parent_y - 10),
                    **{"class": "fork-label"},
                ).text = "fork()"

                # Vertical line down
                ET.SubElement(
                    svg,
                    "line",
                    x1=str(fork_x),
                    y1=str(parent_y),
                    x2=str(fork_x),
                    y2=str(child_y),
                    **{"class": "fork-line"},
                )

                # Horizontal line to child
                ET.SubElement(
                    svg,
                    "line",
                    x1=str(fork_x),
                    y1=str(child_y),
                    x2=str(child_start_x),
                    y2=str(child_y),
                    **{"class": "fork-line"},
                )

    def _save_svg(self, svg: ET.Element, output_file: str) -> None:
        """Save SVG to file."""
        tree = ET.ElementTree(svg)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        print(f"SVG visualization saved to: {output_file}")


class ProcessTreeVisualizer:
    """Main class that coordinates loading, parsing, and rendering."""

    def __init__(self):
        self.parser = RecordingParser()
        self.ascii_renderer = ASCIIRenderer()
        self.svg_renderer = SVGRenderer()

    def load_and_visualize(
        self, recordings_dir: Path, output_svg: Optional[str] = None
    ) -> None:
        """Load recordings and generate visualizations."""
        # Load all recordings
        tree = self._load_recordings(recordings_dir)

        # Generate outputs
        # Generate SVG only if explicitly requested via output_svg parameter
        if output_svg:
            self.svg_renderer.render(tree, output_svg)

        # Always show ASCII output
        self.ascii_renderer.render(tree)

    def _load_recordings(self, recordings_dir: Path) -> ProcessTree:
        """Load all .undo files and build process tree."""
        recording_files = list(recordings_dir.glob("*.undo"))
        if not recording_files:
            raise ValueError(f"No .undo files found in {recordings_dir}")

        print(f"Found {len(recording_files)} recording files")

        tree = ProcessTree()
        for recording_file in recording_files:
            pid, ppid, start_time = self.parser.extract_process_info(recording_file)
            if pid is not None:
                process = Process(pid, ppid, str(recording_file), start_time)
                tree.add_process(process)
                print(
                    f"Loaded: PID {pid}, PPID {ppid}, Start: {start_time:.9f}, File: {recording_file.name}"
                )

        tree.build_relationships()
        return tree


if HAS_GDB:

    class ProcessTreeCommand(gdb.Command):
        """
        Visualize process trees from .undo recording files.

        Usage: process-tree RECORDINGS_DIR [--output-svg FILE]

        Arguments:
            RECORDINGS_DIR: Directory containing .undo recording files

        Options:
            --output-svg FILE: Output SVG file path (generates SVG in addition to ASCII)

        By default, only ASCII tree output is shown. Use --output-svg to also generate an SVG.

        Examples:
            process-tree /path/to/recordings
            process-tree /path/to/recordings --output-svg tree.svg
        """

        def __init__(self):
            super().__init__("process-tree", gdb.COMMAND_USER, gdb.COMPLETE_FILENAME)

        def invoke(self, argument, from_tty):
            """Execute the process-tree command."""
            if not argument:
                raise gdb.GdbError(
                    "Usage: process-tree RECORDINGS_DIR [--output-svg FILE]"
                )

            # Parse arguments
            args = shlex.split(argument)
            recordings_dir = Path(args[0]).expanduser()
            output_svg = None

            # Parse optional arguments
            i = 1
            while i < len(args):
                if args[i] == "--output-svg":
                    if i + 1 >= len(args):
                        raise gdb.GdbError("--output-svg requires a filename")
                    output_svg = str(Path(args[i + 1]).expanduser())
                    i += 2
                else:
                    raise gdb.GdbError(f"Unknown argument: {args[i]}")

            # Validate recordings directory
            if not recordings_dir.exists() or not recordings_dir.is_dir():
                raise gdb.GdbError(f"Error: {recordings_dir} is not a valid directory")

            # Check if undo is available
            try:
                check_undo_available()
            except FileNotFoundError as e:
                raise gdb.GdbError(str(e))

            # Create visualizer and generate output
            try:
                visualizer = ProcessTreeVisualizer()
                visualizer.load_and_visualize(recordings_dir, output_svg)
            except Exception as e:
                raise gdb.GdbError(f"Error generating process tree: {e}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Visualize process trees from .undo recording files. "
        "By default, only ASCII output is shown."
    )
    parser.add_argument(
        "recordings_dir", help="Directory containing .undo recording files"
    )
    parser.add_argument(
        "--output-svg", help="Output SVG file path (generates SVG in addition to ASCII)"
    )

    args = parser.parse_args()

    # Check if undo is available
    try:
        check_undo_available()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1

    recordings_dir = Path(args.recordings_dir).expanduser()
    if not recordings_dir.exists() or not recordings_dir.is_dir():
        print(f"Error: {recordings_dir} is not a valid directory", file=sys.stderr)
        return 1

    output_svg = str(Path(args.output_svg).expanduser()) if args.output_svg else None

    visualizer = ProcessTreeVisualizer()
    try:
        visualizer.load_and_visualize(recordings_dir, output_svg)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1

    return 0


# When sourced by GDB, register the command
if HAS_GDB:
    ProcessTreeCommand()
# When run as a standalone script
if __name__ == "__main__":
    sys.exit(main())
