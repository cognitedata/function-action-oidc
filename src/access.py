from __future__ import annotations

import logging
from dataclasses import dataclass
from os import linesep
from typing import Any, Dict, Iterable, Iterator, List, NoReturn

from cognite.client.data_classes.iam import TokenInspection
from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient

from exceptions import MissingAclError
from utils import retrieve_dataset

logger = logging.getLogger(__name__)


def verify_credentials_vs_project(client: CogniteClient, project: str, cred_name: str) -> TokenInspection:
    try:
        token_inspect = client.iam.token.inspect()
    except CogniteAPIError:
        logger.error(
            f"Unable to call 'token/inspect'. Probable cause: {cred_name.title()} credentials wrong or missing "
            "one or more capabilities! Requires both 'Projects:LIST' and 'Groups:LIST'!"
        )
        raise
    # Check that given project is in the list of authenticated projects:
    if project not in (valid_projects := [p.url_name for p in token_inspect.projects]):
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
    scope: Dict[str, Any]
    projects: List[str]

    @classmethod
    def from_dict(cls, dct: Dict[str, Any]) -> Capability:
        projects = dct.pop("projectScope")["projects"]
        (acl,) = dct  # magic voodoo syntax to extract the only key
        return cls(acl=acl, projects=projects, **dct[acl])

    def is_all_scope(self) -> bool:
        return "all" in self.scope

    def is_dataset_scope(self, id: int) -> bool:
        return id in map(int, self.scope.get("datasetScope", {}).get("ids", []))

    def is_ids_scope(self, id: int) -> bool:
        return id in map(int, self.scope.get("idScope", {}).get("ids", []))


def parse_capabilities_from_token_inspect_for_project(token_inspect: TokenInspection, project: str):
    return list(filter(lambda c: project in c.projects, map(Capability.from_dict, token_inspect.capabilities)))


def filter_capabilities(capabilities: Iterable[Capability], acl: str) -> Iterator[Capability]:
    return filter(lambda c: c.acl == acl, capabilities)


def missing_function_capabilities(capabilities: Iterable[Capability]) -> List[str]:
    actions = set(a for c in filter_capabilities(capabilities, acl="functionsAcl") for a in c.actions)
    if missing := set(["READ", "WRITE"]) - actions:
        return [f"functionsAcl:{m} (scope: 'all')" for m in missing]
    return []


def missing_session_capabilities(capabilities: Iterable[Capability]) -> List[str]:
    actions = set(a for c in filter_capabilities(capabilities, acl="sessionsAcl") for a in c.actions)
    if "CREATE" not in actions:
        return ["sessionsAcl:CREATE (scope: 'all')"]
    return []


def missing_files_capabilities(
    capabilities: Iterable[Capability], client: CogniteClient, ds_id: int = None
) -> List[str]:
    files_capes = list(filter_capabilities(capabilities, acl="filesAcl"))
    files_actions_all_scope = set(a for c in files_capes for a in c.actions if c.is_all_scope())
    missing_files_acl = set(["READ", "WRITE"]) - files_actions_all_scope

    if ds_id is None:
        # Not using a data set, so we require Files:READ/WRITE in scope=ALL:
        if missing_files_acl:
            return [f"filesAcl:{m} (scope: 'all') (Tip: consider using a data set!)" for m in missing_files_acl]
        return []

    # If using a data set, we also accept *it* as scope for files:
    missing_acls = []
    files_actions_dsid_scope = set(a for c in files_capes for a in c.actions if c.is_dataset_scope(ds_id))
    if missing_files_acl := missing_files_acl - files_actions_dsid_scope:
        missing_acls += [f"filesAcl:{m} (scope: 'all' OR 'dataset: {ds_id}')" for m in missing_files_acl]

    data_set_capes = filter_capabilities(capabilities, acl="datasetsAcl")
    data_set_actions = set(a for c in data_set_capes for a in c.actions if c.is_all_scope() or c.is_ids_scope(ds_id))
    if "READ" not in data_set_actions:
        # No read access to the given data set, so we can't check if it is write protected:
        missing_acls.append(f"datasetsAcl:READ (scope: 'all' OR 'id: {ds_id}')")
        if "OWNER" not in data_set_actions:
            missing_acls.append("(If dataset is write protected, you'll also need OWNER)")
        return missing_acls

    if retrieve_dataset(client, ds_id).write_protected:
        if "OWNER" not in data_set_actions:
            missing_acls.append(f"datasetsAcl:OWNER (scope: 'all' OR 'id: {ds_id}'). NB: 'all scope' not recommended!")
    return missing_acls


def verify_schedule_creds_capabilities(token_inspect: TokenInspection, project: str) -> None:
    capabilities = parse_capabilities_from_token_inspect_for_project(token_inspect, project)
    missing = missing_session_capabilities(capabilities)
    if missing:
        raise_on_missing(missing, "schedule")
    logger.info("Schedule credentials capabilities verified!")


def verify_deploy_capabilites(
    token_inspect: TokenInspection,
    client: CogniteClient,
    project: str,
    ds_id: int = None,
) -> None:
    capabilities = parse_capabilities_from_token_inspect_for_project(token_inspect, project)
    missing = missing_function_capabilities(capabilities) + missing_files_capabilities(capabilities, client, ds_id)
    if missing:
        raise_on_missing(missing, "deploy")
    logger.info("Deploy credentials capabilities verified!")


def raise_on_missing(missing: List[str], cred_type: str) -> NoReturn:
    missing_info = linesep.join(f"- {i}: {s}" for i, s in enumerate(missing, 1))
    raise MissingAclError(
        f"{cred_type.upper()} credentials missing one (or more) required capabilities:\n{missing_info}"
    )
