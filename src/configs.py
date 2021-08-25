import logging
from contextlib import suppress
from inspect import signature
from os import getenv
from pathlib import Path
from typing import Dict, List, Optional

from cognite.client.exceptions import CogniteAPIError
from pydantic import BaseModel, Field, constr, root_validator, validator
from schedula import FunctionSchedule
from yaml import safe_load

from utils import NonEmptyString, NonEmptyStringMax128, create_oidc_client, decode_and_parse, verify_path_is_directory

logger = logging.getLogger(__name__)


class GithubActionModel(BaseModel):
    class Config:
        allow_population_by_field_name = True

    @classmethod
    def from_envvars(cls):
        """Magic parameter-load from env.vars. (Github Action Syntax)"""

        def get_parameter(val):
            # GitHub action passes all missing arguments as empty strings:
            return getenv(f"INPUT_{val.upper()}") or None

        return cls.parse_obj({k: get_parameter(k) for k in cls.schema()["properties"]})


class DeleteFunctionConfig(GithubActionModel):
    remove_only: bool
    function_external_id: NonEmptyString

    def __bool__(self):
        return self.remove_only


class CredentialsMixin:
    @property
    def credentials(self) -> Dict[str, str]:
        return self.dict(include={"client_id", "client_secret"})

    @property
    def experimental_client(self):
        return create_oidc_client(**self.dict(by_alias=False, include=set(signature(create_oidc_client).parameters)))


class DeployCredentials(GithubActionModel, CredentialsMixin):
    cdf_project: Optional[NonEmptyString]
    cdf_cluster: NonEmptyString
    client_id: NonEmptyString = Field(alias="deployment_client_id")
    tenant_id: NonEmptyString = Field(alias="deployment_tenant_id")
    client_secret: NonEmptyString = Field(alias="deployment_client_secret")


class SchedulesConfig(GithubActionModel, CredentialsMixin):
    schedule_file: Optional[constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- /]+\.ya?ml$")]  # noqa: F722
    client_id: Optional[NonEmptyString] = Field(alias="schedules_client_id")
    client_secret: Optional[NonEmptyString] = Field(alias="schedules_client_secret")
    tenant_id: Optional[NonEmptyString] = Field(alias="schedules_tenant_id")
    cdf_cluster: Optional[NonEmptyString]
    schedules: Optional[List[FunctionSchedule]]

    @root_validator(skip_on_failure=True)
    def verify_schedule_credentials_are_given(cls, values):
        if values["schedule_file"] is None:
            return values
        # If schedules are given, credentials must be set:
        c_secret, c_id, t_id = values["client_secret"], values["client_id"], values["tenant_id"]
        if None in [c_secret, c_id, t_id]:
            raise ValueError(
                "Schedules created for OIDC functions require additional client credentials (to be used  at runtime). "
                "Missing one or more of ['schedules_client_secret', 'schedules_client_id', 'schedules_tenant_id']"
            )
        return values


class FunctionConfig(GithubActionModel):
    function_external_id: NonEmptyString
    function_folder: Path
    function_secrets: Optional[Dict[str, str]]
    function_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- ]+\.(py|js)$")  # noqa: F722
    common_folder: Optional[Path]
    data_set_external_id: Optional[str]
    cpu: Optional[float]
    memory: Optional[float]
    owner: Optional[NonEmptyStringMax128]
    function_description: Optional[NonEmptyStringMax128]

    def create_fn_params(self):
        return {
            "secrets": self.function_secrets,
            "name": self.function_external_id,
            "external_id": self.function_external_id,
            "function_path": self.function_file,
            "owner": self.owner,
            "cpu": self.cpu,
            "memory": self.memory,
            "description": self.function_description,
        }

    @validator("function_secrets")
    def validate_and_parse_secret(cls, value):
        if value is None:
            return value
        try:
            return decode_and_parse(value)
        except Exception as e:
            raise ValueError(
                "Invalid secret, must be a valid base64 encoded JSON. See the README: "
                "https://github.com/cognitedata/function-action-oidc#function-secrets"
            ) from e

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


class RunConfig(BaseModel):
    schedule: SchedulesConfig
    function: FunctionConfig

    @staticmethod
    def verify_single_credential(cred_config, name):
        try:
            client = cred_config.experimental_client
            res = client.iam.token.inspect()
            # TODO: Is this really how to project??
            logger.info(f"{name.title()} credentials verified towards {res.projects[0].url_name}!")
        except CogniteAPIError:
            raise ValueError(
                f"{name.title()} credentials wrong or missing capabilities! (Test endpoint: /token/inspect)"
            )

    @root_validator(skip_on_failure=True)
    def verify_credentials(cls, values):
        cls.verify_single_credential(values["function"], name="deploy")
        if values["schedule"].schedule_file is None:
            cls.verify_single_credential(values["schedule"], name="schedule")

    @root_validator(skip_on_failure=True)
    def verify_and_parse_schedules(cls, values) -> List[FunctionSchedule]:
        if (schedule_file := values["schedule"].schedule_file) is None:
            values["schedule"].schedules = []
            return values

        path = values["function"].function_folder / schedule_file
        if not path.is_file():
            values["schedule"].schedules = []
            values["schedule"].schedule_file = None
            logger.warning(f"Ignoring given schedule file '{schedule_file}', path does not exist: {path.absolute()}")
        else:
            with path.open() as f:
                values["schedule"].schedules = list(map(FunctionSchedule.parse_obj, safe_load(f)))
        return values
