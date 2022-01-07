import ast
import logging
from pathlib import Path
from typing import List

from configs import FunctionConfig
from exceptions import FunctionValidationError

logger = logging.getLogger(__name__)


HANDLE_ARGS = ("data", "client", "secrets", "function_call_info")


def run_checks(config: FunctionConfig) -> None:
    # Python-only checks:
    if config.function_file.endswith(".py"):
        _check_handle_args(config.function_folder / config.function_file)


class HandleVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.handle_found = False
        self.fn_names: List[str] = []

    def visit_FunctionDef(self, fn_def):
        """Overridden to get root function definitions only."""
        self.fn_names.append(name := fn_def.name)  # The things we do for nice error messages
        if name != "handle":
            return
        if self.handle_found:
            logger.error(err_msg := "Multiple function definitions found!")
            raise FunctionValidationError(err_msg)

        bad_args = set(param.arg for param in fn_def.args.args).difference(HANDLE_ARGS)
        if not bad_args:
            logger.info(f"Signature of function entrypoint, 'handle', in file '{self.file_path}' validated!")
            self.handle_found = True
        else:
            err_msg = (
                f"In file '{self.file_path}', function 'handle' contained illegal args: {list(bad_args)}. "
                f"The function args must be a subset of: {list(HANDLE_ARGS)} (ordering does NOT matter!)"
            )
            logger.error(err_msg)
            raise FunctionValidationError(err_msg)


def _check_handle_args(file_path: Path, fn_name: str = "handle") -> None:
    # If missing raises FileNotFoundError, which is a perfectly fine error message
    with file_path.open() as f:
        file = f.read()

    (node_visitor := HandleVisitor(file_path)).visit(ast.parse(file))
    if not node_visitor.handle_found:
        err_msg = (
            f"Required function named '{fn_name}' was not found in file '{file_path}' "
            f"(functions found: {node_visitor.fn_names})."
        )
        logger.error(err_msg)
        raise FunctionValidationError(err_msg)
