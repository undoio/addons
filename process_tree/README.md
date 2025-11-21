# Process Tree

Visualizes process trees from Undo recordings. Shows both ASCII tree output and SVG timeline diagrams of parent-child process relationships.

Note: this addon was created with Claude Code and has had only minimal human review and testing.

## Usage

This addon can be used in two ways:

### As a UDB Command

Before using the command it must be loaded into the debugger:
```
extend process-tree
```

Then use the command:
```
process-tree RECORDINGS_DIR [--output-svg FILE]
```

**Arguments:**
- `RECORDINGS_DIR`: Directory containing .undo recordings.

**Options:**
- `--output-svg FILE`: Output SVG file path

**Note:** By default, only ASCII tree output is shown. Use `--output-svg` to also generate an SVG visualization.

### As a Standalone Script

```bash
./process_tree.py RECORDINGS_DIR [--output-svg FILE]
```

## Examples

**Basic usage** (shows ASCII output only):
```
process-tree /path/to/recordings
```

**Generate SVG visualization**:
```
process-tree /path/to/recordings --output-svg my_tree.svg
```

## Output

The addon can generate two types of visualizations:

### ASCII Tree
A hierarchical text representation of the process tree showing parent-child relationships:
```
Process Tree Visualization:
==================================================
└── PID 1234 (recording_0001.undo)
    ├── PID 1235 (recording_0002.undo)
    │   └── PID 1237 (recording_0004.undo)
    └── PID 1236 (recording_0003.undo)
```

### SVG Timeline
A visual timeline diagram showing:
- Horizontal timeline for each process
- Fork points showing where new processes are created
- Process IDs and recording file names
- Parent-child relationships with connecting lines

The SVG file can be viewed in any web browser or image viewer.

