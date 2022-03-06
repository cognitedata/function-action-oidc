import logging
from functools import cached_property
from os import getenv
from pathlib import Path
from typing import Dict, List, Optional

from crontab import CronSlices
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, Json, NonNegativeFloat, NonNegativeInt, root_validator, validator
from yaml import safe_load  # type: ignore

from access import verify_deploy_capabilites, verify_schedule_creds_capabilities
from defaults import (
    DEFAULT_FUNCTION_DEPLOY_TIMEOUT,
    DEFAULT_FUNCTION_FILE,
    DEFAULT_POST_DEPLOY_CLEANUP,
    DEFAULT_REMOVE_ONLY,
    DEFAULT_TOKEN_SCOPES,
    DEFAULT_TOKEN_URL,
)
from utils import (
    FnFileString,
    NonEmptyString,
    NonEmptyStringMax128,
    NonEmptyStringMax500,
    ToLowerStr,
    YamlFileString,
    create_oidc_client_from_dct,
    decode_and_parse,
    verify_path_is_directory,
)

logger = logging.getLogger(__name__)

if RUNNING_IN_GITHUB_ACTION := getenv("GITHUB_ACTIONS") == "true":
    logger.info("Inferred current runtime environment to be 'Github Actions'.")
if RUNNING_IN_AZURE_PIPE := getenv("TF_BUILD") == "True":
    logger.info("Inferred current runtime environment to be 'Azure Pipelines'.")

if RUNNING_IN_GITHUB_ACTION is RUNNING_IN_AZURE_PIPE:  # Hacky XOR
    raise RuntimeError(
        "Unable to unambiguously infer the current runtime environment. Please create an "
        "issue on Github: https://github.com/cognitedata/function-action-oidc/"
    )


class BaseModel(PydanticBaseModel):
    class Config:
        allow_population_by_field_name = True
        # Workaround for 'functools.cached_property' to work with pydantic:
        keep_untouched = (cached_property,)


class FunctionSchedule(BaseModel):
    name: NonEmptyString
    description: Optional[NonEmptyString]
    cron_expression: NonEmptyString = Field(alias="cron")
    data: Optional[Dict]

    @validator("cron_expression")
    def validate_cron(cls, cron):
        if not CronSlices.is_valid(cron):
            raise ValueError(f"Invalid cron expression: '{cron}'")
        return cron


class PipelineModel(BaseModel):
    @classmethod
    def from_envvars(cls):
        """Magic parameter-load from env.vars. (...which is how most workflows pass params)"""

        def get_parameter(key, prefix=""):
            if RUNNING_IN_AZURE_PIPE:
                prefix = ""  # Just to point out no prefix in Azure
            elif RUNNING_IN_GITHUB_ACTION:
                prefix = "INPUT_"
            # Missing args passed as empty strings, load as `None` instead:
            return getenv(f"{prefix}{key.upper()}", "").strip() or None

        expected_params = cls.schema()["properties"]
        return cls.parse_obj(
            {k: v for k, v in zip(expected_params, map(get_parameter, expected_params)) if v is not None}
        )


class DeleteFunctionConfig(PipelineModel):
    remove_only: bool = DEFAULT_REMOVE_ONLY
    function_external_id: NonEmptyString

    def __bool__(self):
        return self.remove_only


class CredentialsModel(BaseModel):
    cdf_project: NonEmptyString
    cdf_cluster: NonEmptyString

    @property
    def credentials(self) -> Dict[str, str]:
        return self.dict(include={"client_id", "client_secret"})

    @cached_property
    def experimental_client(self):
        return create_oidc_client_from_dct(self.dict(by_alias=False))

    @root_validator(skip_on_failure=True)
    def verify_oidc_params(cls, values):
        tenant_id, token_url, token_scopes = values["tenant_id"], values["token_url"], values["token_scopes"]
        cred_type = cls.credentials_type()
        if tenant_id is not None:
            if token_url is None:
                values["token_url"] = DEFAULT_TOKEN_URL.format(tenant_id)
            else:
                logger.warning(
                    f"Both '{cred_type}_token_url' and '{cred_type}_tenant_id' were provided; "
                    f"'{cred_type}_tenant_id' will be ignored!"
                )
        elif token_url is None and cred_type == "deployment":  # Schedules credentials are optional
            raise ValueError("Either 'deployment_token_url' OR 'deployment_tenant_id' must be provided!")

        if token_scopes is None:
            values["token_scopes"] = [DEFAULT_TOKEN_SCOPES.format(values["cdf_cluster"])]
        return values


class DeployCredentials(PipelineModel, CredentialsModel):
    client_id: NonEmptyString = Field(alias="deployment_client_id")
    tenant_id: Optional[NonEmptyString] = Field(alias="deployment_tenant_id")
    client_secret: NonEmptyString = Field(alias="deployment_client_secret")
    token_scopes: Optional[Json[List[str]]] = Field(alias="deployment_token_scopes")
    token_url: Optional[NonEmptyString] = Field(alias="deployment_token_url")
    token_custom_args: Optional[Json[Dict[str, str]]] = Field(alias="deployment_token_custom_args")
    data_set_id: Optional[int]  # For acl/capability checks only

    @classmethod
    def credentials_type(cls) -> str:  # Just used for error msgs
        return "deployment"

    @root_validator(skip_on_failure=True)
    def verify_credentials_and_capabilities(cls, values):
        client = create_oidc_client_from_dct(values)
        project = values["cdf_project"]
        data_set_id = values["data_set_id"]
        verify_deploy_capabilites(client, project, ds_id=data_set_id)
        return values


class SchedulesConfig(PipelineModel, CredentialsModel):
    schedule_file: Optional[YamlFileString]
    client_id: Optional[NonEmptyString] = Field(alias="schedules_client_id")
    client_secret: Optional[NonEmptyString] = Field(alias="schedules_client_secret")
    tenant_id: Optional[NonEmptyString] = Field(alias="schedules_tenant_id")
    token_scopes: Optional[Json[List[str]]] = Field(alias="schedules_token_scopes")
    token_url: Optional[NonEmptyString] = Field(alias="schedules_token_url")
    token_custom_args: Optional[Json[Dict[str, str]]] = Field(alias="schedules_token_custom_args")
    function_folder: Path
    schedules: Optional[List[FunctionSchedule]]

    @classmethod
    def credentials_type(cls) -> str:  # Just used for error msgs
        return "schedules"

    @root_validator(skip_on_failure=True)
    def verify_schedule_file_and_parse(cls, values):
        if (schedule_file := values["schedule_file"]) is None:
            values["schedules"] = []
            return values

        if (path := values["function_folder"] / schedule_file).is_file():
            with path.open() as f:
                if schedules := safe_load(f):
                    values["schedules"] = list(map(FunctionSchedule.parse_obj, schedules))
                    return values
                logger.warning(f"Given schedule file '{schedule_file}' appears empty and was ignored")
        else:
            logger.warning(f"Ignoring given schedule file '{schedule_file}', path does not exist: {path.absolute()}")
        values.update({"schedule_file": None, "schedules": []})
        return values

    @root_validator(skip_on_failure=True)
    def verify_schedule_credentials(cls, values):
        if values["schedule_file"] is None:
            return values

        # A valid schedule file is given; schedule-credentials are thus required:
        if values["client_secret"] is None or values["client_id"] is None:
            raise ValueError(
                "When using OIDC functions with schedules, additional client credentials to be used at runtime "
                "are required. Missing at least one of ['schedules_client_secret', 'schedules_client_id']."
            )
        elif values["token_url"] is None:
            raise ValueError(
                "When using OIDC functions with schedules, either 'schedules_token_url' OR 'schedules_tenant_id' "
                "must be provided!"
            )
        client = create_oidc_client_from_dct(values)
        project = values["cdf_project"]
        verify_schedule_creds_capabilities(client, project)
        return values


class FunctionConfig(PipelineModel):
    function_external_id: NonEmptyString
    function_folder: Path
    function_secrets: Optional[Dict[str, str]]
    function_file: FnFileString = DEFAULT_FUNCTION_FILE
    function_deploy_timeout: NonNegativeInt = DEFAULT_FUNCTION_DEPLOY_TIMEOUT
    common_folder: Optional[Path]
    post_deploy_cleanup: bool = DEFAULT_POST_DEPLOY_CLEANUP
    data_set_id: Optional[int]
    cpu: Optional[NonNegativeFloat]
    memory: Optional[NonNegativeFloat]
    owner: Optional[NonEmptyStringMax128]
    description: Optional[NonEmptyStringMax500]
    env_vars: Optional[Json[Dict[str, str]]]
    runtime: Optional[ToLowerStr]

    def create_fn_params(self):
        return {
            "secrets": self.function_secrets,
            "name": self.function_external_id,
            "external_id": self.function_external_id,
            "function_path": self.function_file,
            "owner": self.owner,
            "cpu": self.cpu,
            "memory": self.memory,
            "description": self.description,
            "env_vars": self.env_vars,
            "runtime": self.runtime,
        }

    @validator("function_secrets", pre=True)
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
        verify_path_is_directory(values["function_folder"], "function_folder")

        if (common_folder := values["common_folder"]) is None:
            logger.info("No 'common code' directory added to the function!")
        else:
            verify_path_is_directory(common_folder, "common_folder")
        return values


class RunConfig(BaseModel):
    deploy_creds: DeployCredentials
    schedule: SchedulesConfig
    function: FunctionConfig
