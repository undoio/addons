import sys

from . import _gdbtypes as gdbtypes, events

from typing import *

BP_ACCESS_WATCHPOINT: gdbtypes.BreakpointType
BP_BREAKPOINT: gdbtypes.BreakpointType
BP_HARDWARE_WATCHPOINT: gdbtypes.BreakpointType
BP_NONE: gdbtypes.BreakpointType
BP_READ_WATCHPOINT: gdbtypes.BreakpointType
BP_WATCHPOINT: gdbtypes.BreakpointType

COMMAND_BREAKPOINTS: gdbtypes.CommandClassType
COMMAND_DATA: gdbtypes.CommandClassType
COMMAND_FILES: gdbtypes.CommandClassType
COMMAND_MAINTENANCE: gdbtypes.CommandClassType
COMMAND_NONE: gdbtypes.CommandClassType
COMMAND_OBSCURE: gdbtypes.CommandClassType
COMMAND_RUNNING: gdbtypes.CommandClassType
COMMAND_STACK: gdbtypes.CommandClassType
COMMAND_STATUS: gdbtypes.CommandClassType
COMMAND_SUPPORT: gdbtypes.CommandClassType
COMMAND_TRACEPOINTS: gdbtypes.CommandClassType
COMMAND_USER: gdbtypes.CommandClassType

COMPLETE_COMMAND: gdbtypes.CommandCompleteType
COMPLETE_EXPRESSION: gdbtypes.CommandCompleteType
COMPLETE_FILENAME: gdbtypes.CommandCompleteType
COMPLETE_LOCATION: gdbtypes.CommandCompleteType
COMPLETE_NONE: gdbtypes.CommandCompleteType
COMPLETE_SYMBOL: gdbtypes.CommandCompleteType

FRAME_UNWIND_INNER_ID: gdbtypes.FrameUnwindType
FRAME_UNWIND_MEMORY_ERROR: gdbtypes.FrameUnwindType
FRAME_UNWIND_NO_REASON: gdbtypes.FrameUnwindType
FRAME_UNWIND_NO_SAVED_PC: gdbtypes.FrameUnwindType
FRAME_UNWIND_NULL_ID: gdbtypes.FrameUnwindType
FRAME_UNWIND_OUTERMOST: gdbtypes.FrameUnwindType
FRAME_UNWIND_SAME_ID: gdbtypes.FrameUnwindType
FRAME_UNWIND_UNAVAILABLE: gdbtypes.FrameUnwindType

DUMMY_FRAME: gdbtypes.FrameType
INLINE_FRAME: gdbtypes.FrameType
NORMAL_FRAME: gdbtypes.FrameType
ARCH_FRAME: gdbtypes.FrameType
SENTINEL_FRAME: gdbtypes.FrameType
SIGTRAMP_FRAME: gdbtypes.FrameType
TAILCALL_FRAME: gdbtypes.FrameType

PARAM_AUTO_BOOLEAN: gdbtypes.ParameterClassType
PARAM_BOOLEAN: gdbtypes.ParameterClassType
PARAM_ENUM: gdbtypes.ParameterClassType
PARAM_FILENAME: gdbtypes.ParameterClassType
PARAM_INTEGER: gdbtypes.ParameterClassType
PARAM_OPTIONAL_FILENAME: gdbtypes.ParameterClassType
PARAM_STRING: gdbtypes.ParameterClassType
PARAM_STRING_NOESCAPE: gdbtypes.ParameterClassType
PARAM_UINTEGER: gdbtypes.ParameterClassType
PARAM_ZINTEGER: gdbtypes.ParameterClassType
PARAM_ZUINTEGER: gdbtypes.ParameterClassType
PARAM_ZUINTEGER_UNLIMITED: gdbtypes.ParameterClassType

STDERR: gdbtypes.StandardIOType
STDLOG: gdbtypes.StandardIOType
STDOUT: gdbtypes.StandardIOType

SYMBOL_FUNCTIONS_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_LABEL_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_STRUCT_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_TYPES_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_UNDEF_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_VARIABLES_DOMAIN: gdbtypes.SymbolDomainType
SYMBOL_VAR_DOMAIN: gdbtypes.SymbolDomainType

SYMBOL_LOC_ARG: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_BLOCK: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_COMPUTED: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_CONST: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_CONST_BYTES: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_LABEL: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_LOCAL: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_OPTIMIZED_OUT: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_REF_ARG: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_REGISTER: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_REGPARM_ADDR: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_STATIC: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_TYPEDEF: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_UNDEF: gdbtypes.SymbolAddressClassType
SYMBOL_LOC_UNRESOLVED: gdbtypes.SymbolAddressClassType

TYPE_CODE_ARRAY: gdbtypes.ValueTypeCodeType
TYPE_CODE_BITSTRING: gdbtypes.ValueTypeCodeType
TYPE_CODE_BOOL: gdbtypes.ValueTypeCodeType
TYPE_CODE_CHAR: gdbtypes.ValueTypeCodeType
TYPE_CODE_COMPLEX: gdbtypes.ValueTypeCodeType
TYPE_CODE_DECFLOAT: gdbtypes.ValueTypeCodeType
TYPE_CODE_ENUM: gdbtypes.ValueTypeCodeType
TYPE_CODE_ERROR: gdbtypes.ValueTypeCodeType
TYPE_CODE_FLAGS: gdbtypes.ValueTypeCodeType
TYPE_CODE_FLT: gdbtypes.ValueTypeCodeType
TYPE_CODE_FUNC: gdbtypes.ValueTypeCodeType
TYPE_CODE_INT: gdbtypes.ValueTypeCodeType
TYPE_CODE_INTERNAL_FUNCTION: gdbtypes.ValueTypeCodeType
TYPE_CODE_MEMBERPTR: gdbtypes.ValueTypeCodeType
TYPE_CODE_METHOD: gdbtypes.ValueTypeCodeType
TYPE_CODE_METHODPTR: gdbtypes.ValueTypeCodeType
TYPE_CODE_NAMESPACE: gdbtypes.ValueTypeCodeType
TYPE_CODE_PTR: gdbtypes.ValueTypeCodeType
TYPE_CODE_RANGE: gdbtypes.ValueTypeCodeType
TYPE_CODE_REF: gdbtypes.ValueTypeCodeType
TYPE_CODE_RVALUE_REF: gdbtypes.ValueTypeCodeType
TYPE_CODE_SET: gdbtypes.ValueTypeCodeType
TYPE_CODE_STRING: gdbtypes.ValueTypeCodeType
TYPE_CODE_STRUCT: gdbtypes.ValueTypeCodeType
TYPE_CODE_TYPEDEF: gdbtypes.ValueTypeCodeType
TYPE_CODE_UNION: gdbtypes.ValueTypeCodeType
TYPE_CODE_VOID: gdbtypes.ValueTypeCodeType

WP_ACCESS: gdbtypes.WatchPointType
WP_READ: gdbtypes.WatchPointType
WP_WRITE: gdbtypes.WatchPointType

HOST_CONFIG: str
TARGET_CONFIG: str
VERSION: str

prompt_hook: Optional[Callable[[str], str]]
pretty_printers: List[gdbtypes.PrettyPrinterFunc]

class Field(object): ...
class error(RuntimeError): ...
class MemoryError(error): ...
class GdbError(Exception): ...
class BlockIterator(object): ...
class Function(object): ...
class Membuf(object): ...
class PendingFrame(object): ...
class TypeIterator(object): ...
class UnwindInfo(object): ...

class Architecture(object):
    def name(self) -> str: ...

class Block(object):
    start: int
    end: int
    function: Optional["Symbol"]
    superblock: Optional["Block"]
    global_block: "Block"
    static_block: "Block"
    is_global: bool
    is_static: bool
    def is_valid(self) -> bool: ...

class Parameter:
    value: Any
    def __init__(
        self,
        name: str,
        command_class: gdbtypes.CommandClassType,
        parameter_class: gdbtypes.ParameterClassType,
        enum_sequence: Sequence[str] = ...,
    ) -> None: ...

class Type(object):  # type: ignore # Ignore that this is named like typing.Type.
    code: gdbtypes.ValueTypeCodeType
    sizeof: int
    tag: Optional[str]
    def array(self, n1: int, n2: int = ...) -> Type: ...
    def const(self) -> Type: ...
    def fields(self) -> Iterable[Field]: ...
    def pointer(self) -> Type: ...
    def range(self) -> Tuple[int, int]: ...
    def reference(self) -> Type: ...
    def strip_typedefs(self) -> Type: ...
    def volatile(self) -> Type: ...
    def target(self) -> Type: ...
    def unqualified(self) -> Type: ...

# Not actually defined by GDB.
_LazyString = Any

class Value(object):
    address: Optional["Value"]
    dynamic_type: Type
    is_lazy: bool
    is_optimized_out: bool
    type: Type
    def __new__(self, val: Any) -> Any: ...
    def __int__(self) -> int: ...
    def __getitem__(self, _n: Any) -> "Value": ...
    def cast(self, type: Type) -> "Value": ...
    def dereference(self) -> "Value": ...
    def dynamic_cast(self, type: Type) -> "Value": ...
    def fetch_lazy(self) -> None: ...
    def format_string(self, *args: Any, **kwargs: Any) -> str: ...
    def referenced_value(self) -> "Value": ...
    def reinterpret_cast(self, type: Type) -> "Value": ...
    def string(self, encoding: str = ..., errors: str = ..., length: int = ...) -> _LazyString: ...

class Breakpoint(object):
    enabled: bool
    silent: bool
    pending: bool
    thread: Optional[int]
    task: Optional[Any]
    ignore_count: int
    number: int
    type: gdbtypes.BreakpointType
    visible: bool
    temporary: bool
    hit_count: int
    location: Optional[str]
    expression: Optional[str]
    condition: Optional[str]
    commands: Optional[str]
    def __init__(
        self,
        spec: str,
        type: gdbtypes.BreakpointType = ...,
        wp_class: gdbtypes.WatchPointType = ...,
        internal: bool = ...,
        temporary: bool = ...,
        qualified: bool = ...,
        source: str = ...,
        function: str = ...,
        label: str = ...,
        line: int = ...,
    ) -> None: ...
    def stop(self) -> bool: ...
    def is_valid(self) -> bool: ...
    def delete(self) -> None: ...

class FinishBreakpoint(Breakpoint): ...

class Symbol(object):
    type: Type
    symtab: "Symtab"
    line: int
    name: str
    linkage_name: str
    print_name: str
    add_class: gdbtypes.SymbolAddressClassType
    needs_frame: bool
    is_argument: bool
    is_constant: bool
    is_function: bool
    is_variable: bool
    def is_valid(self) -> bool: ...
    def value(self, frame: "Frame" = ...) -> Value: ...

class Frame(object):
    def is_valid(self) -> bool: ...
    def name(self) -> Optional[str]: ...
    def architecture(self) -> Architecture: ...
    def type(self) -> int: ...
    def unwind_stop_reason(self) -> int: ...
    def pc(self) -> int: ...
    def block(self) -> Block: ...
    def function(self) -> Optional[Symbol]: ...
    def older(self) -> Optional["Frame"]: ...
    def newer(self) -> Optional["Frame"]: ...
    def range(self) -> Tuple[int, int]: ...
    def read_register(self, register: str) -> Value: ...
    def read_var(self, variable: Union[str, Symbol], block: Block = ...) -> Value: ...
    def select(self) -> None: ...
    def find_sal(self) -> "Symtab_and_line": ...

class Progspace(object):
    filename: Optional[str]
    pretty_printers: List[gdbtypes.PrettyPrinterFunc]
    def block_for_pc(self, pc: int) -> Optional[Block]: ...
    def find_pc_line(self, pc: int) -> "Symtab_and_line": ...
    def is_valid(self) -> bool: ...
    def objfiles(self) -> List["Objfile"]: ...
    def solib_name(self, address: int) -> Optional[str]: ...

class LineTableEntry(object):
    line: int
    pc: int
    is_stmt: int

class LineTable(object):
    def __iter__(self) -> Generator[LineTableEntry, None, None]: ...
    def line(self, line: int) -> Optional[Iterable[LineTableEntry]]: ...
    def has_line(self, line: int) -> bool: ...
    def source_lines(self,) -> List[int]: ...

class LineTableIterator(object): ...

class Objfile(object):
    filename: Optional[str]
    username: Optional[str]
    owner: Optional[str]
    build_id: Optional[str]
    progspace: Progspace
    pretty_printers: List[gdbtypes.PrettyPrinterFunc]
    def is_valid(self) -> bool: ...
    def add_separate_debug_file(self, file: str) -> None: ...

class Symtab(object):
    filename: str
    objfile: Objfile
    producer: Optional[str]
    def is_valid(self) -> bool: ...
    def fullname(self) -> str: ...
    def global_block(self) -> Block: ...
    def static_block(self) -> Block: ...
    def linetable(self) -> LineTable: ...

class Symtab_and_line(object):
    symtab: Optional[Symtab]
    pc: int
    last: Optional[int]
    line: int
    def is_valid(self) -> bool: ...

class Inferior(object):
    num: int
    pid: int
    was_attached: bool
    progspace: Progspace
    def is_valid(self) -> bool: ...
    def threads(self) -> Tuple["InferiorThread", ...]: ...
    def architecture(self) -> Architecture: ...
    def read_memory(self, address: int, length: int) -> Any: ...
    def write_memory(self, address: int, buffer: Any, length: int = ...) -> None: ...
    def search_memory(self, address: int, length: int, pattern: Any) -> Optional[int]: ...

class InferiorThread(object):
    name: Optional[str]
    num: int
    global_num: int
    ptid: Tuple[int, int, int]
    inferior: Inferior
    def is_valid(self) -> bool: ...
    def switch(self) -> None: ...
    def is_stopped(self) -> bool: ...
    def is_running(self) -> bool: ...
    def is_exited(self) -> bool: ...
    def handle(self) -> bytes: ...

class EventRegistry(object):
    def connect(self, function: gdbtypes.EventFunction) -> None: ...
    def disconnect(self, function: gdbtypes.EventFunction) -> None: ...

class Event(object): ...
class ClearObjFilesEvent(Event): ...
class ExitedEvent(Event): ...
class InferiorCallPostEvent(Event): ...
class InferiorCallPreEvent(Event): ...
class MemoryChangedEvent(Event): ...
class RegisterChangedEvent(Event): ...
class ThreadEvent(Event): ...
class ContinueEvent(ThreadEvent): ...
class NewThreadEvent(ThreadEvent): ...
class StopEvent(ThreadEvent): ...

class BreakpointEvent(StopEvent):
    breakpoints: List[Breakpoint]

class SignalEvent(StopEvent): ...

class NewObjFileEvent(Event):
    new_objfile: Objfile

class InferiorDeletedEvent(Event):
    inferior: Inferior

class NewInferiorEvent(Event):
    inferior: Inferior

class Command(object):
    def __init__(
        self,
        name: str,
        command_class: gdbtypes.CommandClassType = ...,
        completer_class: gdbtypes.CommandCompleteType = ...,
        prefix: bool = ...,
        rename_existing_to: str = ...,
    ) -> None: ...
    def dont_repeat(self) -> None: ...
    def invoke(self, argument: str, from_tty: bool) -> None: ...
    def complete(self, text: str, word: str) -> gdbtypes.CompleteResult: ...

# The correct signature for gdb.execute (in upstream GDB) is:
#     def execute(command: str, from_tty: bool = ..., from_string: bool = ...) -> Optional[str]: ...
# With the return value being a string if the to_string argument is true, otherwise it's None.
#
# In our code, we don't want to accidentally use gdb.execute(..., to_string=True) as that doesn't
# produce the expected output if command tracing is on (see help set trace-commands). Instead, we
# must use gdbutils.execute_to_string.
# To avoid accidental usages of the to_string parameter, we just pretend it doesn't exist and that
# the return value is always None.
#
# Our bundled GDB also accepts a boolean argument called styled (see
# https://sourceware.org/pipermail/gdb-patches/2020-December/174340.html), but we don't include
# it here for the same reason as for the `to_string` argument.
def execute(command: str, from_tty: bool = ...) -> None: ...
def block_for_pc(pc: int) -> Optional[Block]: ...
def breakpoints() -> Iterable[Breakpoint]: ...
def current_objfile() -> Optional[Objfile]: ...
def current_progspace() -> Progspace: ...
def find_pc_line(pc: int) -> Symtab_and_line: ...
def flush(stream: gdbtypes.StandardIOType = ...) -> None: ...
def find_pc_compunit_symtabs(pc: int) -> List[Symtab]: ...
def inferiors() -> List[Inferior]: ...
def lookup_global_symbol(
    name: str, domain: gdbtypes.SymbolDomainType = ...
) -> Tuple[Optional[Symbol], bool]: ...
def lookup_objfile(name: str, by_build_id: bool = ...) -> Optional[Objfile]: ...
def lookup_symbol(
    name: str, block: Block = ..., domain: gdbtypes.SymbolDomainType = ...
) -> Tuple[Optional[Symbol], bool]: ...
def lookup_type(name: str, block: Optional[Block] = ...) -> Type: ...
def newest_frame() -> Frame: ...
def objfiles() -> Iterable[Objfile]: ...
def parameter(parameter: str) -> Any: ...
def parse_and_eval(expression: str) -> Value: ...
def progspaces() -> List[Progspace]: ...
def selected_frame() -> Frame: ...
def selected_inferior() -> Inferior: ...
def selected_thread() -> Optional[InferiorThread]: ...
def string_to_argv(arg: str) -> List[str]: ...
def write(string: str, stream: gdbtypes.StandardIOType = ...) -> None: ...
def _execute_file(filepath: str) -> None: ...
