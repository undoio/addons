# Extended event log

Capture all parameters and results of a number of syscalls.
The objective is to make it easier to compare different runs of the same process.

## Usage

```
extended-evt-log [-output OUTPUT-PATH]
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/extended_evt_log/extended_evt_log.py
```

### Optional arguments

- `-output OUTPUT-PATH`, `-o OUTPUT-PATH`:
  Path to a file were to write the reconstructed file. If not specified, the
  content is printed on standard output.

