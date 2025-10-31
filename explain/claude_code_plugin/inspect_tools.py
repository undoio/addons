"""
Dynamically create tool functions by parsing `explain.py` statically using AST.

This avoids the need to import explain.py, which has UDB-specific dependencies
that are not available outside of UDB.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import inspect
import types
from pathlib import Path
from typing import Any, Callable


@dataclasses.dataclass(frozen=True)
class _Parameter:
    """
    Represents a function parameter.
    """

    name: str
    type: type


@dataclasses.dataclass(frozen=True)
class _ToolDefinition:
    """
    Represents a tool method definition.
    """

    name: str
    params: list[_Parameter]
    return_type: type
    docstring: str

    @functools.cached_property
    def as_inspect_signature(self) -> inspect.Signature:
        """
        The function signature for this tool.
        """
        parameters = [
            inspect.Parameter(
                param.name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=param.type,
            )
            for param in self.params
        ]
        # Create and return the signature.
        return inspect.Signature(parameters, return_annotation=self.return_type)


# Map from a base type name to the type itself.
_TYPE_MAP = {
    t.__name__: t
    for t in (
        bool,
        dict,
        float,
        int,
        list,
        set,
        str,
        tuple,
    )
}


def _annotation_to_type(annotation: ast.expr | None) -> type:
    """
    Convert an AST type annotation to an actual Python type.
    """
    match annotation:

        case ast.Constant(value=None):
            return types.NoneType

        case ast.Name(id=name):
            # Basic types like `int`, `str`, `list`, etc.
            try:
                return _TYPE_MAP[name]
            except KeyError as exc:
                raise RuntimeError(f"Unsupported type: {name!r}") from exc

        case ast.Subscript():
            # Generic types like `list[int]`, `dict[str, int]`, etc.
            # The function return type should probably by a `TypeForm` (from `typing_extensions` or
            # from `typing` in Python 3.15 and later), but that's not properly supported by mypy
            # yet.
            base_type: Any = _annotation_to_type(annotation.value)
            match annotation.slice:
                case ast.Tuple():
                    # Multiple type arguments.
                    args = tuple(_annotation_to_type(elt) for elt in annotation.slice.elts)
                    return base_type[args]
                case _:
                    # Single type argument.
                    arg = _annotation_to_type(annotation.slice)
                    return base_type[arg]

        case ast.BinOp(op=ast.BitOr()):
            # Handle `Union` types like `str | None`.
            left = _annotation_to_type(annotation.left)
            right = _annotation_to_type(annotation.right)
            # See the comment about `TypeForm` above.
            return left | right  # type: ignore[return-value]

        case None:
            raise RuntimeError("Missing type annotation")

        case _:
            raise RuntimeError(f"Unsupported annotation: {ast.unparse(annotation)}")


class _ToolExtractor(ast.NodeVisitor):
    """
    Extract tool definitions from UdbMcpGateway class in explain.py.
    """

    @classmethod
    def parse(cls, source: str) -> list[_ToolDefinition]:
        """
        Extract tool definitions from `source` by parsing it statically.
        """
        tree = ast.parse(source)
        self = cls()
        self.visit(tree)
        return self.tools

    def __init__(self) -> None:
        self.tools: list[_ToolDefinition] = []
        self.in_gateway_class = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # pylint: disable=invalid-name
        if node.name == "UdbMcpGateway":
            self.in_gateway_class = True
            self.generic_visit(node)
            self.in_gateway_class = False
        else:
            self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # pylint: disable=invalid-name
        if self.in_gateway_class and node.name.startswith("tool_"):
            tool = self._extract_tool(node)
            self.tools.append(tool)

    def _extract_tool(self, node: ast.FunctionDef) -> _ToolDefinition:
        """
        Extract tool definition from a method AST node.
        """
        # All our wrapped tools required a recording path as first argument.
        params = [_Parameter("recording_path", str)]

        for arg in node.args.args[1:]:  # Skip 'self'.
            param = _Parameter(
                name=arg.arg,
                type=_annotation_to_type(arg.annotation),
            )
            params.append(param)

        params, return_type = self._apply_decorator_effects(
            params,
            _annotation_to_type(node.returns),
            [self._get_decorator_name(dec) for dec in node.decorator_list],
        )

        # Augment docstring to include `recording_path`'s documentation.
        docstring = ast.get_docstring(node)
        assert docstring, f"Tool method {node.name} is missing a docstring."
        try:
            before, after = docstring.split("Params:\n", 1)
        except ValueError:
            before = f"{docstring.strip()}\n\n"
            after = ""
        docstring = before + "Params:\nrecording_path: Path to the Undo recording file\n" + after

        return _ToolDefinition(
            name=node.name.removeprefix("tool_"),
            params=params,
            return_type=return_type,
            docstring=docstring,
        )

    def _get_decorator_name(self, decorator: ast.expr) -> str:
        """
        Extract decorator name from decorator AST node.
        """
        match decorator:
            case ast.Name(id=name):
                return name
            case ast.Call(func=ast.Name(id=name)):
                return name
            case _:
                return ""

    def _apply_decorator_effects(
        self,
        params: list[_Parameter],
        return_type: type,
        decorators: list[str],
    ) -> tuple[list[_Parameter], type]:
        """
        Apply decorator effects to parameters and return type.

        Decorators are applied in reverse order (bottom to top in source).
        """
        for decorator in reversed(decorators):
            match decorator:
                case "chain_of_thought":
                    # Adds 'hypothesis: str' parameter at the beginning.
                    params = [_Parameter("hypothesis", str)] + params
                case "collect_output":
                    # Changes return type to str.
                    return_type = str
                case "source_context":
                    # Changes return type to str.
                    return_type = str
                case "report" if return_type is types.NoneType:
                    # Converts `None` returns to empty string.
                    return_type = str
                case _:
                    # Other decorators don't change the signature.
                    pass

        return params, return_type


def _create_tool_function(tool: _ToolDefinition, invoke_tool: Callable) -> Callable:
    """
    Create and return a tool function dynamically at runtime from a `_ToolDefinition`.
    """

    # Create the function dynamically.
    def tool_function(**kwargs: Any) -> Any:
        # Extract all parameters this tool expects.
        tool_kwargs = {p.name: kwargs[p.name] for p in tool.params if p.name in kwargs}
        return invoke_tool(
            tool.name,
            **tool_kwargs,
        )

    # FastMCP uses introspection to add the tool, so we need to set all the details on the wrapper
    # function.
    tool_function.__name__ = f"tool_{tool.name}"
    tool_function.__signature__ = tool.as_inspect_signature  # type: ignore[attr-defined]
    tool_function.__doc__ = tool.docstring

    return tool_function


def load_tools(invoke_tool: Callable) -> tuple[dict[str, Callable], str]:
    """
    Dynamically create wrapper functions for all tools from the `explain` without importing
    `explain` itself.

    `invoke_tool` is the function that is called to actually invoke the tool. Its arguments
    are the tool name, the recording path and the tool parameters.

    Returns a tuple containing:
    - A dictionary mapping tool names to dynamically created tool functions.
    - The base MCP instructions.
    """
    explain_dir = Path(__file__).parent.parent

    explain_path = explain_dir / "explain.py"
    tool_defs = _ToolExtractor.parse(explain_path.read_text(encoding="utf-8"))
    tools = {tool_def.name: _create_tool_function(tool_def, invoke_tool) for tool_def in tool_defs}

    instructions_path = explain_dir / "instructions.md"
    mcp_instructions = instructions_path.read_text(encoding="utf-8")

    return tools, mcp_instructions
