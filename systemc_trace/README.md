# systemc_trace

UDB commands for SystemC design introspection and tracing.

Automatically creates a trace of all signals and module member variables in design.

Based on https://github.com/ripopov/gdb_systemc_trace


### Limitations
Fixed-point datatypes are not supported yet


## Installation

### Prerequisites
* Undo 8.2 or later, with LiveRecorder
* SystemC 2.3.3 built as .so library with debuginfo (see below)

### Running basic example
1. Ensure that the Undo release directory is on $PATH
2. Download SystemC 2.3.3 https://accellera.org/downloads/standards/systemc
3. Build with debug info:
    ```
    $ tar xvf systemc-2.3.3.tar.gz 
    $ cd systemc-2.3.3/
    $ mkdir build_debug
    $ cd build_debug/
    $ cmake ../ -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_STANDARD=14
    $ make -j8
    # build SystemC examples
    $ make check -j8
    ```
4. Record the example:
    ```
    # it is important to cd into example directory, sometimes they read some files from workdir
    $ (cd examples/sysc/risc_cpu && undo record -o risc_cpu.undo risc_cpu)
    ```
5. Create a vcd file from the recording:
    ```
    $ udb examples/sysc/risc_cpu/risc_cpu.undo
    [...]
    end 1,837,898> extend systemc-trace
    Updating repo cache...
    ...done.
    Installing third-party Python packages...
        pyvcd
    ...done.
    Installing 'systemc-trace'...
    ...done.

    Type "show extend-license systemc-trace" for license information.


    WARNING: The 'systemc-trace' addon is experimental and may be withdrawn or
            changed in incompatible ways at any time.

    end 1,837,898> systemc run risc_cpu.vcd
    # risc_cpu.vcd file will be created
    ```
6. Use GTKWave or other VCD viewer to view generated vcd:
    ```
     $ gtkwave risc_cpu.vcd 
    ```

![risc_cpu](gtkwave.png)

You may want to use vcd_hierarchy_manipulator to create hierarchical VCDs: 
https://github.com/yTakatsukasa/vcd_hierarchy_manipulator

## Tracing only required signals

* `udb RECORDING`
* `systemc list-signals`
* List of all detected signals in design will be printed to console
* Copy required signal names (full hierarchical names) into some file, say signals.txt
* `set signals-file signals.txt`
* `systemc run systemc_trace.vcd`
* systemc_trace.vcd will be created

## Print design tree

* `udb RECORDING`
* `systemc print`
