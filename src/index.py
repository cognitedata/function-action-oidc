import logging
import os

import yaml

from checks import run_checks
from config import FunctionConfig, TenantConfig, create_experimental_cognite_client
from function import delete_single_cognite_function, upload_and_create_function
from github_log_handler import GitHubLogHandler
from schedule import deploy_schedules

# Configure logging:
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(GitHubLogHandler())

logger = logging.getLogger(__name__)


def main(config: FunctionConfig) -> None:
    client = create_experimental_cognite_client(config.tenant)
    if config.remove_only:
        # Delete old function, file and schedules:
        delete_single_cognite_function(client, config.external_id, remove_schedules=True)
        return

    # Run checks, then zip together and upload the code files, then create Function:
    run_checks(config)
    function = upload_and_create_function(client, config)
    logger.info(f"Successfully created and deployed function {config.external_id} with id {function.id}")
    if config.remove_schedules:
        # Normal operation is to always remove all attached schedules and then re-create them:
        deploy_schedules(client, function, config.schedules)
    else:
        # If we did not remove existing schedules, we should also not add new ones. Warn if user gave any:
        if (n_schedules := len(config.schedules)) :
            logger.warning(
                f"Skipping step of deploying schedules ({n_schedules} were given). "
                "Parameter 'remove_schedules=False' was passed, so this is to avoid creating duplicate schedules, "
                "as they do not have an unique identifier."
            )
    # Return output parameter (GitHub magic syntax):
    print(f"::set-output name=function_external_id::{function.external_id}")


def get_param_value(param):
    # GitHub action passes all missing arguments as an empty string:
    return os.getenv(f"INPUT_{param.upper()}") or None


def setup_config() -> FunctionConfig:
    # Use 'action.yaml' as the single source of truth for param names:
    with open("/app/action.yaml") as f:
        inputs = set(yaml.safe_load(f)["inputs"])

    tenant_params = [inp for inp in inputs if inp.startswith("cdf")]
    function_params = inputs.difference(tenant_params)

    return FunctionConfig(
        tenant=TenantConfig(**{p: get_param_value(p) for p in tenant_params}),
        **{p: get_param_value(p) for p in function_params},
    )


if __name__ == "__main__":
    # Function Action, assemble!!
    config = setup_config()
    main(config)
