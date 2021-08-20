import ast
import logging
from pathlib import Path

from config import FunctionConfig

logger = logging.getLogger(__name__)


HANDLE_ARGS = ("data", "client", "secrets", "function_call_info")


class FunctionValidationError(Exception):
    pass


def run_checks(config: FunctionConfig) -> None:
    # Python-only checks:
    if config.function_file.endswith(".py"):
        _check_handle_args(config.function_folder / config.function_file)


def _check_handle_args(file_path: Path, fn_name: str = "handle") -> None:
    # If missing raises FileNotFoundError, which is a perfectly fine error message
    with open(file_path) as file:
        file = file.read()

    for node in ast.walk(ast.parse(file)):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            bad_args = set(param.arg for param in node.args.args).difference(HANDLE_ARGS)
            if not bad_args:
                logger.info(f"Signature of function entrypoint, '{fn_name}', in file '{file_path}' validated!")
                return
            err_msg = (
                f"In file '{file_path}', function '{fn_name}' contained illegal args: {list(bad_args)}. "
                f"The function args must be a strict subset of: {list(HANDLE_ARGS)} (ordering is not important)"
            )
            logger.error(err_msg)
            raise FunctionValidationError(err_msg)

    err_msg = f"No function named '{fn_name}' was found in file '{file_path}'. It is required!"
    logger.error(err_msg)
    raise FunctionValidationError(err_msg)
