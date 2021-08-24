import logging
from functools import cached_property
from os import getenv
from pathlib import Path
from typing import Dict, List, Optional

from cognite.experimental import CogniteClient as ExpCogniteClient
from crontab import CronSlices
from pydantic import BaseModel, Field, constr, validator
from yaml import safe_load

logger = logging.getLogger(__name__)

# Pydantic fields:
NonEmptyString = constr(min_length=1, strip_whitespace=True)  # type: ignore["valid-type"]


class GithubActionModel(BaseModel):
    @classmethod
    def from_envvars(cls):
        """Magic parameter-load from env.vars. (Github Action Syntax)"""

        def get_parameter(val):
            # GitHub action passes all missing arguments as an empty string:
            return getenv(f"INPUT_{val.upper()}") or None

        return cls(**{k: get_parameter(k) for k in cls.schema()["properties"]})


class DeployCredentials(GithubActionModel):
    cdf_project: Optional[NonEmptyString]
    cdf_cluster: NonEmptyString
    deployment_client_id: NonEmptyString
    deployment_tenant_id: NonEmptyString
    deployment_client_secret: NonEmptyString

    @cached_property
    def experimental_client(self):
        return ExpCogniteClient(
            token_url=f"https://login.microsoftonline.com/{self.deployment_tenant_id}/oauth2/v2.0/token",
            token_client_id=self.deployment_client_id,
            token_client_secret=self.deployment_client_secret,
            token_scopes=[f"https://{self.cdf_cluster}.cognitedata.com/.default"],
            project=self.cdf_project,
            base_url=f"https://{self.cdf_cluster}.cognitedata.com",
            client_name="function-action-oidc",
        )


class DeleteFunctionConfig(GithubActionModel):
    remove_only: bool
    function_external_id: NonEmptyString

    def __bool__(self):
        return self.remove_only


class FunctionSchedule(BaseModel):
    class Config:
        allow_population_by_field_name = True

    name: NonEmptyString
    description: Optional[NonEmptyString]
    cron_expression: NonEmptyString = Field(alias="cron")
    data: Optional[Dict]

    @validator("cron_expression")
    def validate_cron(cls, cron):
        if not CronSlices.is_valid(cron):
            raise ValueError(f"Invalid cron expression: '{cron}'")
        return cron


class SchedulesConfig(GithubActionModel):
    schedule_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- /]+\.ya?ml$") = None  # noqa: F722
    schedules_client_secret: Optional[NonEmptyString]
    schedules_client_id: Optional[NonEmptyString]

    @property
    def credentials(self) -> Dict[str, str]:
        return {
            "client_id": self.schedules_client_id,
            "client_secret": self.schedules_client_secret,
        }

    @cached_property
    def schedules(self) -> List[FunctionSchedule]:
        if self.schedule_file is None:
            return []
        path = self.function_folder / self.schedule_file
        with path.open() as f:
            return list(map(FunctionSchedule.parse_obj, safe_load(f)))


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

    def get_memory_and_cpu(self):
        kw = {}
        if self.memory is not None:
            kw["memory"] = self.memory
        if self.cpu is not None:
            kw["cpu"] = self.cpu
        return kw
