import logging
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, List

from cognite.client.data_classes import TokenInspection
from cognite.client.exception import CogniteAPIError

from utils import create_oidc_client_from_dct

logger = logging.getLogger(__name__)


def verify_credentials_vs_project(creds: Dict[str, object], project: str, cred_name: str) -> TokenInspection:
    try:
        client = create_oidc_client_from_dct(creds)
        token_inspect = client.iam.token.inspect()
    except CogniteAPIError:
        raise ValueError(
            f"{cred_name.title()} credentials wrong or missing one or more capabilities! "
            "Requires both 'Projects:LIST' and 'Groups:LIST'!"
        )
    # Check that given project is in the list of authenticated projects:
    if project not in (valid_projects := [p.url_name for p in token_inspect.valid_projects]):
        err_msg = f"{cred_name.title()} credentials NOT verified towards given {project=}, but {valid_projects}!"
        logger.error(err_msg)
        raise ValueError(err_msg)

    logger.info(f"{cred_name.title()} credentials verified towards {project=}!")
    return token_inspect


@dataclass
class Capability:
    acl: str
    version: int
    actions: List[str]
    scope: Dict[str, object]
    projects: List[str]

    @classmethod
    def from_dict(cls, dct):
        projects = dct.pop("projectScope")["projects"]
        (acl,) = dct  # magic voodoo syntax to extract the only key
        return cls(acl=acl, projects=projects, **dct[acl])


def filter_capabilities(capabilities: Iterable[Capability], acl: str) -> Iterator[Capability]:
    return filter(lambda c: c.acl == acl, capabilities)


def missing_function_capabilities(capabilities: Iterable[Capability]):
    actions = set(a for c in filter_capabilities(capabilities, acl="functionsAcl") for a in c.actions)
    if (required := set(["READ", "WRITE"])) == actions:
        return []
    return [f"Functions:{req}" for req in required]


def missing_files_capabilities(capabilities: Iterable[Capability]):
    # files_capes = list(filter_capabilities(capabilities, acl="filesAcl"))
    # TODO: Implement!
    logger.info("FilesAcl capabilities not yet verified (reason: not implemented)!")
    return []


def verify_capabilites(token_inspect: TokenInspection, project: str, cred_name: str) -> None:
    capabilities = list(filter(lambda c: project in c.projects, map(Capability.from_dict, token_inspect.capabilities)))
    missing_capabilites = missing_function_capabilities(capabilities) + missing_files_capabilities(capabilities)
    if missing_capabilites:
        raise ValueError(
            f"{cred_name.title()} credentials missing one or more required capabilities: {missing_capabilites}"
        )
    logger.info(f"{cred_name.title()} credentials capabilities verified!")
