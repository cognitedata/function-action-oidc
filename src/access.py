from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from os import linesep
from typing import AbstractSet, Any, Dict, Iterable, Iterator, List, NoReturn

from cognite.client.data_classes.iam import TokenInspection
from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient

from exceptions import MissingAclError
from utils import inspect_token, retrieve_dataset, retrieve_groups_in_user_scope

logger = logging.getLogger(__name__)


def verify_credentials_vs_project(client: CogniteClient, project: str, cred_name: str) -> None:
    # Check that given project is in the list of authenticated projects:
    if project not in (valid_projs := [p.url_name for p in inspect_token(client).projects]):
        err_msg = f"{cred_name.title()} credentials NOT verified towards given {project=}, but {valid_projs}!"
        logger.error(err_msg)
        raise ValueError(err_msg)

    logger.info(f"{cred_name.title()} credentials verified towards {project=}!")


@dataclass
class Capability:
    acl: str
    actions: List[str]
    scope: Dict[str, Any]

    @classmethod
    def from_dct(cls, dct: Dict[str, Any]) -> Capability:
        (acl,) = dct  # magic voodoo syntax to extract the only key
        return cls(acl=acl, **dct[acl])

    def is_all_scope(self) -> bool:
        return "all" in self.scope

    def is_dataset_scope(self, id: int) -> bool:
        return id in map(int, self.scope.get("datasetScope", {}).get("ids", []))

    def is_ids_scope(self, id: int) -> bool:
        return id in map(int, self.scope.get("idScope", {}).get("ids", []))


def retrieve_and_parse_capabilities(client: CogniteClient, project: str) -> List[Capability]:
    return list(
        map(
            Capability.from_dct,
            (c for group in retrieve_groups_in_user_scope(client) for c in group.capabilities),
        ),
    )


def filter_capabilities(capabs: Iterable[Capability], acl: str) -> Iterator[Capability]:
    return filter(lambda c: c.acl == acl, capabs)


ACL_PROJECT_LIST = "projects:LIST (scope: 'all')"
ACL_GROUPS_LIST = "groups:LIST (scope: 'all' OR 'currentuserscope')"
MISSING_ACLS_WARNING = "(There might be more missing, but need the above-mentioned first to check!)"


def missing_basic_capabilities(client: CogniteClient) -> List[str]:
    try:
        token_inspect = inspect_token(client)
    except CogniteAPIError:
        # This only fails if we are missing BOTH 'project:LIST' and 'groups:LIST':
        return [ACL_PROJECT_LIST, ACL_GROUPS_LIST, MISSING_ACLS_WARNING]

    if token_inspect.projects and token_inspect.capabilities:
        return []
    # We are missing one of the two, but don't know which:
    with suppress(CogniteAPIError):
        retrieve_groups_in_user_scope(client)
        return [ACL_PROJECT_LIST, MISSING_ACLS_WARNING]
    return [ACL_GROUPS_LIST, MISSING_ACLS_WARNING]


def missing_function_capabilities(
    capabs: Iterable[Capability], required_actions: AbstractSet = frozenset(("READ", "WRITE"))
) -> List[str]:
    actions = set(a for c in filter_capabilities(capabs, acl="functionsAcl") for a in c.actions)
    if missing := required_actions - actions:
        return [f"functionsAcl:{m} (scope: 'all')" for m in missing]
    return []


def missing_session_capabilities(capabs: Iterable[Capability]) -> List[str]:
    actions = set(a for c in filter_capabilities(capabs, acl="sessionsAcl") for a in c.actions)
    if "CREATE" not in actions:
        return ["sessionsAcl:CREATE (scope: 'all')"]
    return []


def missing_files_capabilities(capabs: Iterable[Capability], client: CogniteClient, ds_id: int = None) -> List[str]:
    files_capes = list(filter_capabilities(capabs, acl="filesAcl"))
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

    data_set_capes = filter_capabilities(capabs, acl="datasetsAcl")
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


def check_basics_and_retrieve_capabilities(client: CogniteClient, project: str, cred_name: str) -> List[Capability]:
    if missing_basic := missing_basic_capabilities(client):
        raise_on_missing(missing_basic, cred_name)

    return retrieve_and_parse_capabilities(client, project)


def verify_schedule_creds_capabilities(
    client: CogniteClient, project: str, cred_name: str = "schedule"
) -> TokenInspection:
    capabs = check_basics_and_retrieve_capabilities(client, project, cred_name)
    missing = missing_function_capabilities(capabs, required_actions={"WRITE"}) + missing_session_capabilities(capabs)
    if missing:
        raise_on_missing(missing, cred_name)
    logger.info("Schedule credentials capabilities verified!")


def verify_deploy_capabilites(
    client: CogniteClient,
    project: str,
    ds_id: int = None,
    cred_name: str = "deploy",
):
    capabs = check_basics_and_retrieve_capabilities(client, project, cred_name)
    missing = missing_function_capabilities(capabs) + missing_files_capabilities(capabs, client, ds_id)
    if missing:
        raise_on_missing(missing, cred_name)
    logger.info("Deploy credentials capabilities verified!")


def raise_on_missing(missing: List[str], cred_type: str) -> NoReturn:
    missing_info = linesep.join(f"- {i}: {s}" for i, s in enumerate(missing, 1))
    raise MissingAclError(
        f"{cred_type.upper()} credentials missing one (or more) required capabilities:\n{missing_info}"
    )
