import sys

# The import is needed by mypy, but catching the ImportError allows this file to
# be checked by Python 3.
try:
    import _gdb_events as events
except ImportError:
    pass

from typing import (
    Optional,
    NewType,
    Iterable,
    Tuple,
    Any,
    Union,
    Protocol,
    Text,
    Callable,
    List,
    Generator,
    ) 


if sys.version_info[0] > 2:
    # For Python 3.
    long = int


_BreakpointType = NewType('_BreakpointType', int)
BP_ACCESS_WATCHPOINT: _BreakpointType
BP_BREAKPOINT: _BreakpointType
BP_HARDWARE_WATCHPOINT: _BreakpointType
BP_NONE: _BreakpointType
BP_READ_WATCHPOINT: _BreakpointType
BP_WATCHPOINT: _BreakpointType


_CommandClassType = NewType('_CommandClassType', int)
COMMAND_BREAKPOINTS: _CommandClassType
COMMAND_DATA: _CommandClassType
COMMAND_FILES: _CommandClassType
COMMAND_MAINTENANCE: _CommandClassType
COMMAND_NONE: _CommandClassType
COMMAND_OBSCURE: _CommandClassType
COMMAND_RUNNING: _CommandClassType
COMMAND_STACK: _CommandClassType
COMMAND_STATUS: _CommandClassType
COMMAND_SUPPORT: _CommandClassType
COMMAND_TRACEPOINTS: _CommandClassType
COMMAND_USER: _CommandClassType


_CommandCompleteType = NewType('_CommandCompleteType', int)
COMPLETE_COMMAND: _CommandCompleteType
COMPLETE_EXPRESSION: _CommandCompleteType
COMPLETE_FILENAME: _CommandCompleteType
COMPLETE_LOCATION: _CommandCompleteType
COMPLETE_NONE: _CommandCompleteType
COMPLETE_SYMBOL: _CommandCompleteType


_FrameUnwindType = NewType('_FrameUnwindType', int)
FRAME_UNWIND_INNER_ID: _FrameUnwindType
FRAME_UNWIND_MEMORY_ERROR: _FrameUnwindType
FRAME_UNWIND_NO_REASON: _FrameUnwindType
FRAME_UNWIND_NO_SAVED_PC: _FrameUnwindType
FRAME_UNWIND_NULL_ID: _FrameUnwindType
FRAME_UNWIND_OUTERMOST: _FrameUnwindType
FRAME_UNWIND_SAME_ID: _FrameUnwindType
FRAME_UNWIND_UNAVAILABLE: _FrameUnwindType


_FrameType = NewType('_FrameType', int)
DUMMY_FRAME: _FrameType
INLINE_FRAME: _FrameType
NORMAL_FRAME: _FrameType
ARCH_FRAME: _FrameType
SENTINEL_FRAME: _FrameType
SIGTRAMP_FRAME: _FrameType
TAILCALL_FRAME: _FrameType


_StandardIOType = NewType('_StandardIOType', int)
STDERR: _StandardIOType
STDLOG: _StandardIOType
STDOUT: _StandardIOType


_SymbolDomainType = NewType('_SymbolDomainType', int)
SYMBOL_FUNCTIONS_DOMAIN: _SymbolDomainType
SYMBOL_LABEL_DOMAIN: _SymbolDomainType
SYMBOL_STRUCT_DOMAIN: _SymbolDomainType
SYMBOL_TYPES_DOMAIN: _SymbolDomainType
SYMBOL_UNDEF_DOMAIN: _SymbolDomainType
SYMBOL_VARIABLES_DOMAIN: _SymbolDomainType
SYMBOL_VAR_DOMAIN: _SymbolDomainType


_SymbolAddressClassType = NewType('_SymbolAddressClassType', int)
SYMBOL_LOC_ARG: _SymbolAddressClassType
SYMBOL_LOC_BLOCK: _SymbolAddressClassType
SYMBOL_LOC_COMPUTED: _SymbolAddressClassType
SYMBOL_LOC_CONST: _SymbolAddressClassType
SYMBOL_LOC_CONST_BYTES: _SymbolAddressClassType
SYMBOL_LOC_LABEL: _SymbolAddressClassType
SYMBOL_LOC_LOCAL: _SymbolAddressClassType
SYMBOL_LOC_OPTIMIZED_OUT: _SymbolAddressClassType
SYMBOL_LOC_REF_ARG: _SymbolAddressClassType
SYMBOL_LOC_REGISTER: _SymbolAddressClassType
SYMBOL_LOC_REGPARM_ADDR: _SymbolAddressClassType
SYMBOL_LOC_STATIC: _SymbolAddressClassType
SYMBOL_LOC_TYPEDEF: _SymbolAddressClassType
SYMBOL_LOC_UNDEF: _SymbolAddressClassType
SYMBOL_LOC_UNRESOLVED: _SymbolAddressClassType


_ValueTypeCodeType = NewType('_ValueTypeCodeType', int)
TYPE_CODE_ARRAY: _ValueTypeCodeType
TYPE_CODE_BITSTRING: _ValueTypeCodeType
TYPE_CODE_BOOL: _ValueTypeCodeType
TYPE_CODE_CHAR: _ValueTypeCodeType
TYPE_CODE_COMPLEX: _ValueTypeCodeType
TYPE_CODE_DECFLOAT: _ValueTypeCodeType
TYPE_CODE_ENUM: _ValueTypeCodeType
TYPE_CODE_ERROR: _ValueTypeCodeType
TYPE_CODE_FLAGS: _ValueTypeCodeType
TYPE_CODE_FLT: _ValueTypeCodeType
TYPE_CODE_FUNC: _ValueTypeCodeType
TYPE_CODE_INT: _ValueTypeCodeType
TYPE_CODE_INTERNAL_FUNCTION: _ValueTypeCodeType
TYPE_CODE_MEMBERPTR: _ValueTypeCodeType
TYPE_CODE_METHOD: _ValueTypeCodeType
TYPE_CODE_METHODPTR: _ValueTypeCodeType
TYPE_CODE_NAMESPACE: _ValueTypeCodeType
TYPE_CODE_PTR: _ValueTypeCodeType
TYPE_CODE_RANGE: _ValueTypeCodeType
TYPE_CODE_REF: _ValueTypeCodeType
TYPE_CODE_RVALUE_REF: _ValueTypeCodeType
TYPE_CODE_SET: _ValueTypeCodeType
TYPE_CODE_STRING: _ValueTypeCodeType
TYPE_CODE_STRUCT: _ValueTypeCodeType
TYPE_CODE_TYPEDEF: _ValueTypeCodeType
TYPE_CODE_UNION: _ValueTypeCodeType
TYPE_CODE_VOID: _ValueTypeCodeType


_WatchPointType = NewType('_WatchPointType', int)
WP_ACCESS: _WatchPointType
WP_READ: _WatchPointType
WP_WRITE: _WatchPointType


HOST_CONFIG: str
TARGET_CONFIG: str
VERSION: str


class Architecture(object): ...
class Field(object): ...

class error(RuntimeError): ...
class MemoryError(error): ...
class GdbError(Exception): ...

class BlockIterator(object): ...
class Function(object): ...
class InferiorThread(object): ...
class Membuf(object): ...
class Parameter(object): ...
class PendingFrame(object): ...
class TypeIterator(object): ...
class UnwindInfo(object): ...


# Not actually defined by GDB.
class _Thread(object): ...


class Block(object):
    start: long
    end: long
    function: Optional[str]
    superblock: Optional['Block']
    global_block: 'Block'
    static_block: 'Block'
    is_global: bool
    is_static: bool

    def is_valid(self) -> bool: ...


class Type(object): # type: ignore # Ignore that this is named like typing.Type.
    code: _ValueTypeCodeType
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
    address: Optional['Value']
    dynamic_type: Type
    is_lazy: bool
    is_optimized_out: bool
    type: Type

    def __init__(self, val: Any) -> None: ...
    def __int__(self) -> int: ...
    def __getitem__(self, _n: Any) -> 'Value': ...
    def cast(self, type: Type) -> 'Value': ...
    def dereference(self) -> 'Value': ...
    def dynamic_cast(self, type: Type) -> 'Value': ...
    def fetch_lazy(self) -> None: ...
    def format_string(self, *args: Any, **kwargs: Any) -> str: ...
    def referenced_value(self) -> 'Value': ...
    def reinterpret_cast(self, type: Type) -> 'Value': ...
    def string(self, encoding: str = ..., errors: str = ..., length: int = ...) -> _LazyString: ...


class Breakpoint(object):
    enabled: bool
    silent: bool
    pending: bool
    thread: Optional[int]
    task: Optional[Any]
    ignore_count: int
    number: int
    type: _BreakpointType
    visible: bool
    temporary: bool
    hit_count: int
    location: Optional[str]
    expression: Optional[str]
    condition: Optional[str]
    commands: Optional[str]

    def __init__(self, spec: str, type: _BreakpointType = ..., wp_class: _WatchPointType = ...,
                 internal: bool = ..., temporary: bool = ..., qualified: bool = ...,
                 source: str = ..., function: str = ..., label: str = ..., line: int = ...) -> None: ...
    def stop(self) -> bool: ...
    def is_valid(self) -> bool: ...
    def delete(self) -> None: ...


class FinishBreakpoint(Breakpoint): ...


class Symbol(object):
    type: Type
    symtab: Symtab
    line: int
    name: str
    linkage_name: str
    print_name: str
    add_class: _SymbolAddressClassType
    needs_frame: bool
    is_argument: bool
    is_constant: bool
    is_function: bool
    is_variable: bool

    def is_valid(self) -> bool: ...
    def value(self, frame: Frame = ...) -> Value: ...


class Frame(object):
    def is_valid(self) -> bool: ...
    def name(self) -> Optional[str]: ...
    def architecture(self) -> Architecture: ...
    def type(self) -> int: ...
    def unwind_stop_reason(self) -> int: ...
    def pc(self) -> long: ...
    def block(self) -> Block: ...
    def older(self) -> 'Frame': ...
    def newer(self) -> 'Frame': ...
    def read_register(self, register: str) -> Value: ...
    def read_var(self, variable: Union[str, Symbol], block: Block = ...) -> Value: ...
    def select(self) -> None: ...
    def find_sal(self) -> 'Symtab_and_line': ...


class _PrettyPrinter(Protocol):
    def to_string(self) -> Text: ...


_pretty_printer_func = Callable[[Value], Optional[_PrettyPrinter]]


class Progspace(object):
    filename: Optional[str]
    pretty_printers: List[_pretty_printer_func]

    def block_for_pc(self, pc: long) -> Optional[Block]: ...
    def is_valid(self) -> bool: ...
    def objfiles(self) -> List['Objfile']: ...
    def solib_name(self, address: long) -> Optional[str]: ...


class LineTableEntry(object):
    line: int
    pc: long


class LineTable(object):
    def __iter__(self) -> Generator[LineTableEntry, None, None]: ...
    def line(self, line: int) -> Optional[Iterable[LineTableEntry]]: ...
    def has_line(self, line: int) -> bool: ...
    def source_lines(self, ) -> List[long]: ...


class LineTableIterator(object): ...


class Objfile(object):
    filename: Optional[str]
    username: Optional[str]
    owner: Optional[str]
    build_id: Optional[str]
    progspace: Progspace
    pretty_printers: List[_pretty_printer_func]

    def is_valid(self) -> bool: ...


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
    symtab: Symtab
    pc: long
    last: long
    line: int

    def is_valid(self) -> bool: ...


class Inferior(object):
    num: int
    pid: int
    was_attached: bool
    progspace: Progspace

    def is_valid(self) -> bool: ...
    def threads(self) -> Tuple[_Thread, ...]: ...
    def architecture(self) -> Architecture: ...
    def read_memory(self, address: long, length: long) -> Any: ...
    def write_memory(self, address: long, buffer: Any, length: long = ...) -> None: ...
    def search_memory(self, address: long, length: long, pattern: Any) -> Optional[long]: ...


_event_func = Callable[['Event'], None]


class EventRegistry(object):
    def connect(self, _event_func) -> None: ...
    def disconnect(self, _event_func) -> None: ...


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
class BreakpointEvent(StopEvent): ...
class SignalEvent(StopEvent): ...


class NewObjFileEvent(Event):
    new_objfile: Objfile


class InferiorDeletedEvent(Event):
    inferior: Inferior


class NewInferiorEvent(Event):
    inferior: Inferior


_CompleteResult = Union[int, Iterable[str], None]


class Command(object):
    def __init__(self, name: str, command_class: _CommandClassType,
                 completer_class: _CommandCompleteType, prefix: bool) -> None: ...
    def dont_repeat(self) -> None: ...
    def invoke(self, argument: str, from_tty: bool) -> None: ...
    def complete(self, text: str, word: str) -> _CompleteResult: ...


# Any object, including this module itself, with a pretty_printers attribute.
class SupportsPrettyPrinters(Protocol):
    pretty_printers: List[_pretty_printer_func]


def block_for_pc(pc: long) -> Optional[Block]: ...
def breakpoints() -> Iterable[Breakpoint]: ...
def current_objfile() -> Optional[Objfile]: ...
def current_progspace() -> Progspace: ...
def execute(command: str, from_tty: bool = ..., to_string: bool = ...) -> str: ...
def inferiors() -> List[Inferior]: ...
def lookup_global_symbol(name: str, domain: _SymbolDomainType = ...) -> Tuple[Optional[Symbol], bool]: ...
def lookup_objfile(name: str, by_build_id: bool = ...) -> Optional[Objfile]: ...
def lookup_symbol(name: str, block: Block = ..., domain: _SymbolDomainType = ...) -> Tuple[Optional[Symbol], bool]: ...
def lookup_type(name: str, block: Optional[Block] = ...) -> Type: ...
def newest_frame() -> Frame: ...
def objfiles() -> Iterable[Objfile]: ...
def parameter(parameter: str) -> Any: ...
def parse_and_eval(expression: str) -> Value: ...
def pretty_printers() -> List[_pretty_printer_func]: ...
def progspaces() -> List[Progspace]: ...
def selected_frame() -> Frame: ...
def selected_inferior() -> Inferior: ...
def selected_thread() -> _Thread: ...
def string_to_argv(arg: str) -> List[str]: ...
