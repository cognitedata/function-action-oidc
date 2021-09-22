import ast
import logging
from contextlib import suppress
from pathlib import Path

from cognite.client.exceptions import CogniteAPIError, CogniteAPIKeyError

from configs import RunConfig
from exceptions import FunctionValidationError

logger = logging.getLogger(__name__)


HANDLE_ARGS = ("data", "client", "secrets", "function_call_info")


def run_checks(config: RunConfig) -> None:
    # Check 'token_url' is set if we have `Projects:READ`:
    _check_token_url_is_set(config)

    # Python-only checks:
    fn_config = config.function
    if fn_config.function_file.endswith(".py"):
        _check_handle_args(fn_config.function_folder / fn_config.function_file)


def _check_token_url_is_set(config: RunConfig):
    """
    If one of the users credentials happens to have ProjectsAcl:READ, we can verify that
    token URL has been set correctly for the project. Since this Acl is not a requirement for
    functions deployment, we do not raise if missing.
    """
    clients = [config.deploy_creds.experimental_client]
    with suppress(CogniteAPIKeyError):
        # If user is adding schedules, we have additional credentials to try with:
        clients.append(config.schedule.experimental_client)

    for client in clients:
        project = client.config.project
        tenant_id = config.deploy_creds.tenant_id
        try:
            resp = client.get(url=f"/api/v1/projects/{project}")
        except CogniteAPIError:
            continue

        oidc_config = resp.json()["oidcConfiguration"]
        token_url = oidc_config.get("tokenUrl")
        if token_url is not None and tenant_id in token_url:
            return
        else:
            err_msg = (
                f"Project '{project}' OpenID Connect configuration has no token URL. You can fix this by "
                "going to Fusion, Access Management, OpenID Connect then adding the missing field "
                "(Note: Requires `ProjectsAcl:UPDATE`)."
            )
            logger.error(err_msg)
            raise FunctionValidationError(err_msg)


def _check_handle_args(file_path: Path, fn_name: str = "handle") -> None:
    # If missing raises FileNotFoundError, which is a perfectly fine error message
    with file_path.open() as f:
        file = f.read()

    for node in ast.walk(ast.parse(file)):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            bad_args = set(param.arg for param in node.args.args).difference(HANDLE_ARGS)
            if not bad_args:
                logger.info(f"Signature of function entrypoint, '{fn_name}', in file '{file_path}' validated!")
                return
            err_msg = (
                f"In file '{file_path}', function '{fn_name}' contained illegal args: {list(bad_args)}. "
                f"The function args must be a strict subset of: {list(HANDLE_ARGS)} (ordering is not important)"
            )
            logger.error(err_msg)
            raise FunctionValidationError(err_msg)

    err_msg = f"No function named '{fn_name}' was found in file '{file_path}'. It is required!"
    logger.error(err_msg)
    raise FunctionValidationError(err_msg)
