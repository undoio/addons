# Leak detector

Matches all calls to `malloc` and `free` and shows any unmatched `malloc` call
with a Bbcount to jump to.

## Usage
```
ugo start
mleak
```

Before using the script it must be loaded in to the debugger:
```
source PATHTOADDONS/leak_detector/leak_detector.py
```
