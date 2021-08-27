import base64
import json
import logging
import os
from contextlib import contextmanager
from functools import lru_cache
from inspect import signature
from pathlib import Path
from typing import Dict, Optional, Union

from cognite.client.data_classes import DataSet
from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient
from pydantic import constr

logger = logging.getLogger(__name__)


# Pydantic fields:   # type: ignore["valid-type"]
NonEmptyString = constr(min_length=1, strip_whitespace=True)
NonEmptyStringMax128 = constr(min_length=1, max_length=128, strip_whitespace=True)
YamlFileString = constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- /]+\.ya?ml$")  # noqa: F722
FnFileString = constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- ]+\.(py|js)$")  # noqa: F722


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


def decode_and_parse(value: Optional[str]) -> Optional[Dict]:
    if value is None:
        return None
    return json.loads(base64.b64decode(value.encode()))


def verify_path_is_directory(path: Path, parameter: str) -> Path:
    if not path.is_dir():
        raise ValueError(f"Invalid folder path for '{parameter}': '{path}', not a directory!")
    return path


def retrieve_dataset(client: CogniteClient, xid: str) -> DataSet:
    try:
        # Patiently awaiting FilesAPI support of dataset xids...
        if ds := client.data_sets.retrieve(external_id=xid):
            return ds
        raise ValueError(f"No dataset exists with external ID: '{xid}'")

    except CogniteAPIError as exc:
        err_msg = "Unable to retrieve dataset: Deployment credentials is missing capability 'dataset:READ'."
        logger.error(err_msg)
        raise CogniteAPIError(err_msg, exc.code, exc.x_request_id) from None


@lru_cache(None)
def create_oidc_client(
    tenant_id: str, client_id: str, client_secret: str, cdf_cluster: str, cdf_project: str
) -> CogniteClient:
    return CogniteClient(
        token_url=f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        token_client_id=client_id,
        token_client_secret=client_secret,
        token_scopes=[f"https://{cdf_cluster}.cognitedata.com/.default"],
        project=cdf_project,
        base_url=f"https://{cdf_cluster}.cognitedata.com",
        client_name="function-action-oidc",
    )


def create_oidc_client_from_dct(dct):
    return create_oidc_client(**{k: dct[k] for k in signature(create_oidc_client).parameters})
