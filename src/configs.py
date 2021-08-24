import logging
from contextlib import suppress
from functools import cached_property
from inspect import signature
from os import getenv
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, constr, root_validator, validator
from schedula import FunctionSchedule
from yaml import safe_load

from utils import NonEmptyString, create_oidc_client, decode_and_parse, verify_path_is_directory

logger = logging.getLogger(__name__)


class GithubActionModel(BaseModel):
    class Config:
        allow_population_by_field_name = True

    @classmethod
    def from_envvars(cls):
        """Magic parameter-load from env.vars. (Github Action Syntax)"""

        def get_parameter(val):
            # GitHub action passes all missing arguments as an empty string:
            return getenv(f"INPUT_{val.upper()}") or None

        return cls.parse_obj({k: get_parameter(k) for k in cls.schema()["properties"]})


class DeleteFunctionConfig(GithubActionModel):
    remove_only: bool
    function_external_id: NonEmptyString

    def __bool__(self):
        return self.remove_only


class CredentialsModel:
    @property
    def credentials(self) -> Dict[str, str]:
        return self.dict(include={"client_id", "client_secret"})

    def experimental_client(self):
        return create_oidc_client(**self.dict(by_alias=False, include=set(signature(create_oidc_client).parameters)))


class DeployCredentials(GithubActionModel, CredentialsModel):
    cdf_project: Optional[NonEmptyString]
    cdf_cluster: NonEmptyString
    client_id: NonEmptyString = Field(alias="deployment_client_id")
    tenant_id: NonEmptyString = Field(alias="deployment_tenant_id")
    client_secret: NonEmptyString = Field(alias="deployment_client_secret")


class SchedulesConfig(GithubActionModel, CredentialsModel):
    schedule_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- /]+\.ya?ml$") = None  # noqa: F722
    client_id: Optional[NonEmptyString] = Field(alias="schedules_client_id")
    client_secret: Optional[NonEmptyString] = Field(alias="schedules_client_secret")
    tenant_id: Optional[NonEmptyString] = Field(alias="schedules_tenant_id")
    cdf_cluster: Optional[NonEmptyString]

    @cached_property
    def schedules(self) -> List[FunctionSchedule]:
        if self.schedule_file is None:
            return []
        path = self.function_folder / self.schedule_file
        with path.open() as f:
            return list(map(FunctionSchedule.parse_obj, safe_load(f)))

    @root_validator(skip_on_failure=True)
    def verify_schedules(cls, values):
        if (schedule_file := values["schedule_file"]) is None:
            return values
        path = values["function_folder"] / schedule_file
        if not path.is_file():
            values["schedule_file"] = None
            logger.warning(f"Ignoring given schedule file '{schedule_file}', path does not exist: {path.absolute()}")
        return values

    @root_validator(skip_on_failure=True)
    def verify_schedule_credentials(cls, values):
        if values["schedule_file"] is None:
            return values
        # If schedules are given, credentials must be set:
        c_secret, c_id = values["schedules_client_secret"], values["schedules_client_id"]
        if c_secret is None or c_id is None:
            raise ValueError(
                "Schedules created for OIDC functions require additional client credentials (to be used "
                "at runtime). Missing one or both of ['schedules_client_secret', 'schedules_client_id']"
            )
        verify_credentials(c_secret, c_id)
        return values


def verify_credentials(client_secret: str, client_id: str) -> None:
    pass  # TODO


class FunctionConfig(GithubActionModel):
    function_external_id: NonEmptyString
    function_folder: Path
    function_secrets: Optional[Dict[str, str]]
    function_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- ]+\.(py|js)$")  # noqa: F722
    common_folder: Optional[Path]
    data_set_external_id: Optional[str]
    cpu: Optional[float]
    memory: Optional[float]
    owner: constr(min_length=1, max_length=128, strip_whitespace=True) = None

    @property
    def secrets(self) -> Optional[Dict[str, str]]:
        return self.function_secrets

    def get_memory_and_cpu(self):
        kw = {}
        if self.memory is not None:
            kw["memory"] = self.memory
        if self.cpu is not None:
            kw["cpu"] = self.cpu
        return kw

    @validator("function_secrets")
    def validate_and_parse_secret(cls, value):
        if value is None:
            return value
        try:
            return decode_and_parse(value)
        except Exception as e:
            raise ValueError("Invalid secret, must be a valid base64 encoded JSON") from e

    @root_validator(skip_on_failure=True)
    def check_function_folders(cls, values):
        verify_path_is_directory(values["function_folder"])

        if (common_folder := values["common_folder"]) is not None:
            verify_path_is_directory(common_folder)
        else:
            # Try default directory 'common/':
            with suppress(ValueError):
                values["common_folder"] = verify_path_is_directory(Path("common"))
        return values
