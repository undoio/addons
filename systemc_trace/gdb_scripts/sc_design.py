# coding=utf-8
# Created by ripopov
from __future__ import print_function
import subprocess
import sys
from typing import Any

# Temporary local install of pyvcd
import pathlib
pyvcd_dir = pathlib.Path("/tmp/pyvcd")
pyvcd_dir.mkdir(exist_ok=True)
subprocess.check_call(["pip", "install", "--upgrade", "--target", str(pyvcd_dir), "pyvcd"])
sys.path.append(str(pyvcd_dir))
import vcd

import gdb_hacks
import sc_trace
import stdlib_hacks

import gdb

def is_sc_object(val_type):
    return gdb_hacks.is_type_compatible(val_type, "sc_core::sc_object")


def is_sc_module(val_type):
    return gdb_hacks.is_type_compatible(val_type, "sc_core::sc_module")


def __is_module_or_interface(mtype):
    tname = mtype.strip_typedefs().name
    return tname in ("sc_core::sc_module", "sc_core::sc_interface")


def __get_plain_data_fields_rec(mtype, res):
    for field in mtype.fields():
        if field.is_base_class:
            if not __is_module_or_interface(field.type):
                __get_plain_data_fields_rec(field.type, res)
        elif not field.artificial:
            if not is_sc_object(field.type):
                res.append(field)

    return res


def get_plain_data_fields(mtype):
    res = []
    __get_plain_data_fields_rec(mtype, res)
    return res


def get(gdb_value: gdb.Value):
    real_type = gdb_value.type.strip_typedefs()

    size_bit = 8 * real_type.sizeof

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

        elif real_type.name == "sc_core::sc_clock" or real_type.name.startswith("sc_core::sc_signal<"):
            # refresh
            v = gdb_value.address.dereference()
            return v['m_cur_val']

        elif gdb_hacks.is_type_compatible(real_type, "sc_core::sc_method_process"):
            return None

        elif gdb_hacks.is_type_compatible(real_type, "sc_core::sc_thread_process"):
            return None

        elif real_type.name.startswith("sc_core::sc_in<") or real_type.name.startswith("sc_core::sc_out<"):
            m_interface = gdb_value['m_interface']
            m_interface = m_interface.reinterpret_cast(m_interface.dynamic_type)
            return m_interface.dereference()

        # elif real_type.code == gdb.TYPE_CODE_STRUCT and not real_type.name.startswith("sc_core::") \
        #         and not real_type.name.startswith("sc_dt::") and not real_type.name.startswith("std::"):
        #     for member in gdb_hacks.get_data_member_list(gdb_value):
        #         self.trace(member[0], name + "*" + member[1])

        else:
            raise ("Type not supported yet: " + real_type.name)
            pass

class StoppingTracer:

    def __init__(self, trace_file_name) -> None:
        self.trace_file_name = trace_file_name
        self.traced_signals: list[tuple[gdb.Value,str, Any]] = []
        self.trace_file = open(self.trace_file_name, "w")
        # FIXME timescale
        # FIXME date
        self.writer = vcd.VCDWriter(self.trace_file, timescale='1 ns', date='today')

    def done(self):
        self.writer.close()
        self.trace_file.close()

    def trace(self, value: gdb.Value, name):

        split_name = name.rsplit(".", maxsplit=1)
        if len(split_name) == 1:
            scope = ""
            leafname = name
        else:
            scope = split_name[0]
            leafname = split_name[1]
        # FIXME init value?
        t = value.type
        try:
            t = t.template_argument(0)
        except:
            pass

        if t.code == gdb.TYPE_CODE_INT:
            width = 32
        elif t.code == gdb.TYPE_CODE_BOOL:
            width = 1
        else:
            print(f"Unknown type {t}")
            return
        vcd_var = self.writer.register_var(scope, leafname, 'wire', size=width)
        self.traced_signals.append((value, name, vcd_var))

    def collect(self, simctx):
        bp_trace = gdb.Breakpoint("sc_simcontext::do_timestep")
        for l in bp_trace.locations:
            if "@plt" in l.function:
                l.enabled = False

        while True:
            output = gdb.execute("continue", to_string=True)
            if "Have reached end of recorded history" in output:
                break
            time_stamp = simctx['m_curr_time']['m_value']
            for value, name, vcd_var in self.traced_signals:
                while value.type.code == gdb.TYPE_CODE_STRUCT:
                    value = get(value)
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




class SCModuleMember(object):
    def __init__(self, val, name):
        self.value = val
        self.name = name

    def basename(self):
        return str(self.name).split('.')[-1]


class SCModule(object):

    def __init__(self, gdb_value):
        self.child_modules = []
        self.members = []
        self.name = ""
        self.value = gdb_value.cast(gdb_value.dynamic_type.strip_typedefs())
        assert self.value.address

        if gdb_value.type.name == 'sc_core::sc_simcontext':
            self.__init_from_simctx()
        elif is_sc_module(gdb_value.type):
            self.__init_from_sc_module()
        else:
            assert False

    def _add_child_or_fail(self, child):
        try:
            # FIXME Sometimes this gives "Cannot access memory"
            self.members.append(SCModuleMember(child, str(child['m_name'])[1:-1]))
        except:
            print("Could not read name: skipping")

    def __init_from_simctx(self):
        m_child_objects = stdlib_hacks.StdVectorView(self.value['m_child_objects'])
        self.name = "SYSTEMC_ROOT"

        for child_ptr in m_child_objects:
            child = child_ptr.dereference()
            child = child.cast(child.dynamic_type.strip_typedefs())

            if is_sc_module(child.type):
                self.child_modules.append(SCModule(child))
            else:
                self._add_child_or_fail(child)

    def __init_from_sc_module(self):
        self.name = str(self.value['m_name'])[1:-1]

        m_child_objects_vec = stdlib_hacks.StdVectorView(self.value['m_child_objects'])

        for child_ptr in m_child_objects_vec:
            child = child_ptr.dereference()
            child = child.cast(child.dynamic_type)

            if is_sc_module(child.dynamic_type):
                self.child_modules.append(SCModule(child))
            else:
                self._add_child_or_fail(child)

        for field in get_plain_data_fields(self.value.type):
            self.members.append(SCModuleMember(self.value[field.name], self.name + "." + field.name))

    def basename(self):
        return str(self.name).split('.')[-1]

    def __to_string(self, prefix):
        res = self.basename() + '    (' + str(self.value.dynamic_type.name) + ')'

        n_child_mods = len(self.child_modules)

        member_prefix = "│" if n_child_mods else " "

        for member in self.members:

            icon = " ○ "
            if is_sc_object(member.value.type):
                icon = " ◘ "

            res += "\n" + prefix + member_prefix + icon + member.basename() + "    (" + str(
                member.value.type.name) + ")     "

        for ii in range(0, n_child_mods):

            pref0 = "├"
            pref1 = "│"

            if ii == n_child_mods - 1:
                pref0 = "└"
                pref1 = " "

            res += "\n" + prefix + pref0 + "──" + self.child_modules[ii].__to_string(prefix + pref1 + "  ")

        return res

    def __str__(self):
        return self.__to_string("")

    def print_members(self):
        for member in self.members:
            print (member.name)

        for child_mod in self.child_modules:
            child_mod.print_members()

    def trace_all_tf(self, tracer):
        for member in self.members:
            tracer.trace(member.value, member.name)

        for child_mod in self.child_modules:
            child_mod.trace_all_tf(tracer)

    def trace_all(self, trace_file_name, recording=False):
        print ("tracing all members: ", trace_file_name)
        if recording:
            tf = StoppingTracer(trace_file_name)
        else:
            tf = sc_trace.SCTrace(trace_file_name)
        self.trace_all_tf(tf)
        return tf

    def trace_signal_tf(self, tracer, signal_path):
        if len(signal_path) > 1:
            child_mod = [mod for mod in self.child_modules if mod.basename() == signal_path[0]]
            assert len(child_mod) == 1
            child_mod[0].trace_signal_tf(tracer, signal_path[1:])
        else:
            selected_members = [member for member in self.members if member.basename() == signal_path[0]]
            if len(selected_members) == 1:
                tracer.trace(selected_members[0].value, selected_members[0].name)

    def trace_signals(self, trace_file_name, signal_list, recording=False):
        print ("tracing selected signals: ", trace_file_name)
        if recording:
            tf = StoppingTracer(trace_file_name)
        else:
            tf = sc_trace.SCTrace(trace_file_name)
        for signal_name in signal_list:
            signal_path = signal_name.strip().split('.')
            self.trace_signal_tf(tf, signal_path)
        return tf


