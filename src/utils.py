import base64
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional, Union

# from cognite.experimental import CogniteClient
from pydantic import constr

NonEmptyString = constr(min_length=1, strip_whitespace=True)


@contextmanager
def temporary_chdir(path: Union[str, Path]):
    old_path = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_path)


def create_zipfile_name(function_name: str) -> str:
    return function_name.replace("/", "-") + ".zip"  # Forward-slash is not allowed in file names


def decode_and_parse(value) -> Optional[Dict]:
    if value is None:
        return None
    decoded = base64.b64decode(value.encode())
    return json.loads(decoded)


def verify_path_is_directory(path):
    if not path.is_dir():
        raise ValueError(f"Invalid folder path: '{path}', not a directory!")
    return path
