import logging

from cognite.experimental import CogniteClient

from checks import run_checks
from configs import DeleteFunctionConfig, DeployCredentials, FunctionConfig, RunConfig, SchedulesConfig
from orchestrator import remove_function_with_file, upload_and_create_function
from schedule import deploy_schedules
from setup_logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main(
    client: CogniteClient,
    config: RunConfig,
) -> None:
    # Run static analysis / other checks and pre-deployment verifications:
    run_checks(config.function)

    # Deploy code to Cognite Functions:
    fn = upload_and_create_function(client, config.function)

    # Deploy schedules (if any):
    deploy_schedules(client, fn, config.schedule)

    # Return output parameter (GitHub magic syntax):
    print(f"::set-output name=function_external_id::{fn.external_id}")


if __name__ == "__main__":
    deploy_creds = DeployCredentials.from_envvars()
    client = deploy_creds.experimental_client

    # We have a short-cut for when we only need to delete a function:
    if delete_config := DeleteFunctionConfig.from_envvars():
        remove_function_with_file(client, delete_config.function_external_id)
    else:
        config = RunConfig(
            function=FunctionConfig.from_envvars(),
            schedule=SchedulesConfig.from_envvars(),
        )
        # Function Action OIDC, assemble!!
        main(client, config)
