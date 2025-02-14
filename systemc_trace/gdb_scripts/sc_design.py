# coding=utf-8
# Created by ripopov
# Modified by Undo

from pathlib import Path
from typing import Any

import gdb
import vcd

from . import gdb_hacks, stdlib_hacks


def is_sc_object(val_type: gdb.Type) -> bool:
    """Return True if the type is (subclassed from) sc_object."""
    return gdb_hacks.is_type_compatible(val_type, "sc_core::sc_object")


def is_sc_module(val_type: gdb.Type) -> bool:
    """Return True if the type is (subclassed from) sc_module."""
    return gdb_hacks.is_type_compatible(val_type, "sc_core::sc_module")


def __is_module_or_interface(mtype: gdb.Type) -> bool:
    tname = mtype.strip_typedefs().name
    return tname in ("sc_core::sc_module", "sc_core::sc_interface")


def __get_plain_data_fields_rec(
    mtype: gdb.Type, res: list[gdb.Field] | None = None
) -> list[gdb.Field]:
    res = res or []
    for field in mtype.fields():
        if field.is_base_class:
            if field.type and not __is_module_or_interface(field.type):
                __get_plain_data_fields_rec(field.type, res)
        elif not field.artificial:
            if field.type and not is_sc_object(field.type):
                res.append(field)

    return res


def get_plain_data_fields(mtype: gdb.Type) -> list[gdb.Field]:
    """List all the data members of the given type (including all base classes)."""
    return __get_plain_data_fields_rec(mtype)


def get(gdb_value: gdb.Value) -> gdb.Value | None:
    """Get the current value of the given object.

    For basic types, the value itself is returned. For more complex objects such as
    signals and wires, the value is located somwhere inside."""

    real_type = gdb_value.type.strip_typedefs()

    if real_type.name and gdb_value.address:
        if real_type.name == "char":
            return gdb_value

        elif real_type.name == "signed char":
            return gdb_value

        elif real_type.name == "short":
            return gdb_value

        elif real_type.name == "int":
            return gdb_value

        elif real_type.name == "long":
            return gdb_value

        elif real_type.name == "long long":
            return gdb_value

        elif real_type.name == "unsigned char":
            return gdb_value

        elif real_type.name == "unsigned short":
            return gdb_value

        elif real_type.name == "unsigned int":
            return gdb_value

        elif real_type.name == "unsigned long":
            return gdb_value

        elif real_type.name == "unsigned long long":
            return gdb_value

        elif real_type.name == "bool":
            return gdb_value

        elif real_type.name == "float":
            return gdb_value

        elif real_type.name == "double":
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_bit"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_logic"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_int_base"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_uint_base"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_signed"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_unsigned"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_bv_base"):
            return gdb_value

        elif gdb_hacks.is_type_compatible(real_type, "sc_dt::sc_lv_base"):
            return gdb_value

        elif real_type.name == "sc_core::sc_clock" or real_type.name.startswith(
            "sc_core::sc_signal<"
        ):
            # refresh
            v = gdb_value.address.dereference()
            return v["m_cur_val"]

        elif gdb_hacks.is_type_compatible(real_type, "sc_core::sc_method_process"):
            return None

        elif gdb_hacks.is_type_compatible(real_type, "sc_core::sc_thread_process"):
            return None

        elif real_type.name.startswith("sc_core::sc_in<") or real_type.name.startswith(
            "sc_core::sc_out<"
        ):
            m_interface = gdb_value["m_interface"]
            m_interface = m_interface.reinterpret_cast(m_interface.dynamic_type)
            return m_interface.dereference()

        else:
            raise TypeError("Type not supported yet: " + real_type.name)

    return None


class Collector:
    """Tool for extracting signal traces by inspecting debuggee state."""

    def __init__(self, timescale: int, trace_file_name: Path) -> None:

        self.trace_file_name = trace_file_name
        self.traced_signals: list[tuple[gdb.Value, str, Any]] = []
        self.trace_file = open(self.trace_file_name, "w")  # pylint: disable=consider-using-with

        # timescale is in femtoseconds
        _t = int(timescale)
        index = 0
        while _t % 1000 == 0:
            _t //= 1000
            index += 1

        suffixes = ["fs", "ps", "ns", "us", "ms", "s"]
        timescale_str = f"{_t} {suffixes[index]}"

        # FIXME date
        self.writer = vcd.VCDWriter(
            self.trace_file, timescale=timescale_str, date="today"
        )

    def done(self) -> None:
        """Declare tracing complete."""
        self.writer.close()
        self.trace_file.close()

    def trace(self, value: gdb.Value, name: str) -> None:
        """Add a variable to be traced."""

        elements = name.split(".")
        leafname = elements[-1]
        scope = ".".join(["SystemC"] + elements[:-1])

        # FIXME init value?
        t = value.type
        if t.name and t.name.startswith("sc_core::sc_clock"):
            # sc_clock is-a sc_signal
            for f in t.fields():
                if (
                    f.is_base_class
                    and f.name
                    and f.name.startswith("sc_core::sc_signal")
                    and f.type
                ):
                    t = f.type
                    break

        if t.name and any(
            t.name.startswith(s)
            for s in ["sc_core::sc_signal", "sc_core::sc_in", "sc_core::sc_out"]
        ):
            base_type = t.template_argument(0)
            assert isinstance(base_type, gdb.Type)
            t = base_type

        if t.code == gdb.TYPE_CODE_INT:
            width = 32
        elif t.code == gdb.TYPE_CODE_BOOL:
            width = 1
        else:
            print(f"Unknown type {t}")
            return
        vcd_var = self.writer.register_var(scope, leafname, "wire", size=width)
        self.traced_signals.append((value, name, vcd_var))

    def collect_now(self, simctx: gdb.Value) -> None:
        time_stamp = int(simctx["m_curr_time"]["m_value"])
        for value, _, vcd_var in self.traced_signals:
            while value.type.code == gdb.TYPE_CODE_STRUCT:
                new_value = get(value)
                if new_value is None:
                    break
                value = new_value
            if value is None:
                continue

            if value.type.code == gdb.TYPE_CODE_INT:
                actual = int(value)
            elif value.type.code == gdb.TYPE_CODE_BOOL:
                actual = bool(value)
            else:
                print(f"Unknown type {value.type} ({value.type})")
            # FIXME time units are probably wrong
            # FIXME casting everything to int
            self.writer.change(vcd_var, time_stamp, actual)


class SCModuleMember:
    def __init__(self, val: gdb.Value, name: str) -> None:
        self.value = val
        self.name = name

    def basename(self) -> str:
        return self.name.split(".")[-1]


class SCModule:

    def __init__(self, gdb_value: gdb.Value) -> None:
        self.child_modules: list[SCModule] = []
        self.members: list[SCModuleMember] = []
        self.name = ""
        self.value = gdb_value.cast(gdb_value.dynamic_type.strip_typedefs())
        assert self.value.address

        if gdb_value.type.name == "sc_core::sc_simcontext":
            self.__init_from_simctx()
        elif is_sc_module(gdb_value.type):
            self.__init_from_sc_module()
        else:
            assert False

    def _add_child_or_fail(self, child: gdb.Value) -> None:
        try:
            # FIXME Sometimes this gives "Cannot access memory"
            self.members.append(SCModuleMember(child, str(child["m_name"])[1:-1]))
        except Exception:
            print("Could not read name: skipping")

    def __init_from_simctx(self) -> None:
        m_child_objects = stdlib_hacks.StdVectorView(self.value["m_child_objects"])
        self.name = "SYSTEMC_ROOT"

        for child_ptr in m_child_objects:
            child = child_ptr.dereference()
            child = child.cast(child.dynamic_type.strip_typedefs())

            if is_sc_module(child.type):
                self.child_modules.append(SCModule(child))
            else:
                self._add_child_or_fail(child)

    def __init_from_sc_module(self) -> None:
        self.name = str(self.value["m_name"])[1:-1]

        m_child_objects_vec = stdlib_hacks.StdVectorView(self.value["m_child_objects"])

        for child_ptr in m_child_objects_vec:
            child = child_ptr.dereference()
            child = child.cast(child.dynamic_type)

            if is_sc_module(child.dynamic_type):
                self.child_modules.append(SCModule(child))
            else:
                self._add_child_or_fail(child)

        for field in get_plain_data_fields(self.value.type):
            if field.name:
                self.members.append(
                    SCModuleMember(self.value[field.name], self.name + "." + field.name)
                )

    def basename(self) -> str:
        return str(self.name).rsplit(".", maxsplit=1)[-1]

    def to_string(self, prefix: str) -> str:
        res = self.basename() + "    (" + str(self.value.dynamic_type.name) + ")"

        n_child_mods = len(self.child_modules)

        member_prefix = "│" if n_child_mods else " "

        for member in self.members:

            icon = " ○ "
            if is_sc_object(member.value.type):
                icon = " ◘ "

            res += (
                "\n"
                + prefix
                + member_prefix
                + icon
                + member.basename()
                + "    ("
                + str(member.value.type.name)
                + ")     "
            )

        for ii in range(0, n_child_mods):

            pref0 = "├"
            pref1 = "│"

            if ii == n_child_mods - 1:
                pref0 = "└"
                pref1 = " "

            res += (
                "\n"
                + prefix
                + pref0
                + "──"
                + self.child_modules[ii].to_string(prefix + pref1 + "  ")
            )

        return res

    def __str__(self) -> str:
        return self.to_string("")

    def print_members(self) -> None:
        for member in self.members:
            print(member.name)

        for child_mod in self.child_modules:
            child_mod.print_members()

    def trace_all_tf(self, tracer: Collector) -> None:
        for member in self.members:
            tracer.trace(member.value, member.name)

        for child_mod in self.child_modules:
            child_mod.trace_all_tf(tracer)

    def trace_all(self, timescale: int, trace_file_name: Path) -> Collector:
        print("tracing all members: ", trace_file_name)
        tf = Collector(timescale, trace_file_name)
        self.trace_all_tf(tf)
        return tf

    def trace_signal_tf(self, tracer: Collector, signal_path: list[str]) -> None:
        if len(signal_path) > 1:
            child_mod = [
                mod for mod in self.child_modules if mod.basename() == signal_path[0]
            ]
            assert len(child_mod) == 1
            child_mod[0].trace_signal_tf(tracer, signal_path[1:])
        else:
            selected_members = [
                member for member in self.members if member.basename() == signal_path[0]
            ]
            if len(selected_members) == 1:
                tracer.trace(selected_members[0].value, selected_members[0].name)

    def trace_signals(
        self, timescale: int, trace_file_name: Path, signal_list: list[str]
    ) -> Collector:
        print("tracing selected signals: ", trace_file_name)
        tf = Collector(timescale, trace_file_name)
        for signal_name in signal_list:
            signal_path = signal_name.strip().split(".")
            self.trace_signal_tf(tf, signal_path)
        return tf
