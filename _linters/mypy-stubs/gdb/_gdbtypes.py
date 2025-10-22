"""
Type definitions for the :mod:`gdb` module.

This is useful for linting code using the module.
"""

from typing import Any, Callable, Iterable, NewType, Optional, Union

# Import from typing once we use Python 3.8.
from typing_extensions import Protocol


BreakpointType = NewType("BreakpointType", int)
CommandClassType = NewType("CommandClassType", int)
CommandCompleteType = NewType("CommandCompleteType", int)
FrameUnwindType = NewType("FrameUnwindType", int)
FrameType = NewType("FrameType", int)
ParameterClassType = NewType("ParameterClassType", int)
StandardIOType = NewType("StandardIOType", int)
SymbolDomainType = NewType("SymbolDomainType", int)
SymbolAddressClassType = NewType("SymbolAddressClassType", int)
ValueTypeCodeType = NewType("ValueTypeCodeType", int)
WatchPointType = NewType("WatchPointType", int)


class PrettyPrinterProtocol(Protocol):
    def to_string(self) -> str: ...


PrettyPrinterFunc = Callable[[Any], Optional[PrettyPrinterProtocol]]

EventFunction = Callable[[Any], None]

CompleteResult = Union[int, Iterable[str], None]
