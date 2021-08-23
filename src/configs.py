import logging
from functools import cached_property
from os import getenv
from pathlib import Path
from typing import Dict, Optional

from cognite.experimental import CogniteClient as ExpCogniteClient
from pydantic import BaseModel, constr

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


class SchedulesConfig(GithubActionModel):
    schedule_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- /]+\.ya?ml$") = None  # noqa: F722
    schedules_client_secret: Optional[NonEmptyString]
    schedules_client_id: Optional[NonEmptyString]


class FunctionConfig(GithubActionModel):
    function_external_id: NonEmptyString
    function_folder: Path
    function_secrets: Dict[str, str] = None
    function_file: constr(min_length=1, strip_whitespace=True, regex=r"^[\w\- ]+\.(py|js)$")  # noqa: F722
    common_folder: Path = None
    data_set_external_id: str = None
    cpu: float = None
    memory: float = None
    owner: constr(min_length=1, max_length=128, strip_whitespace=True) = None
