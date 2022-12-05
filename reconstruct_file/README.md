# Reconstruct file

Reconstruct a file read by the target program by examining its execution
history. Use the `-regex` or `-fd` options to select which file to reconstruct
or, if omitted, the first file opened is reconstructed.

## Usage

```
reconstruct-file [-regex PATH-REGEX | -fd FILE-DESCRIPTOR]
                 [-from-start]
                 [-output OUTPUT-PATH]
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/reconstruct_file/reconstruct_file.py
```

### Optional arguments

- `-regex PATH-REGEX`:
  A regular expression matching the path of the file to reconstruct. Only the
  first file matching the regular expression is considered.
- `-fd FILE-DESCRIPTOR`:
  The file descriptor of the file to reconstruct.
- `-from-start`:
  By default, the file is reconstructed starting at the current time in
  execution history. With this flag, the execution history is considered from
  its beginning.
- `-output OUTPUT-PATH`, `-o OUTPUT-PATH`:
  Path to a file were to write the reconstructed file. If not specified, the
  content is printed on standard output.

## Limitations

- Only 64-bit x86 is supported.
- Only files which are read in their entirety can be fully reconstructed.
- Seeks in files being read are ignored. If the target program uses `fseek` or
  similar, then the file won't be reconstructed correctly.
- Regular expressions matching the whole path (including directories) may
  not match opened files correctly due to path manipulation in the target
  program.
- Signals may cause the command to fail in unexpected ways.
