import logging

from cognite.experimental import CogniteClient

from checks import run_checks
from configs import DeleteFunctionConfig, DeployCredentials, FunctionConfig, SchedulesConfig
from function import remove_function_with_file, upload_and_create_function
from schedule import deploy_schedules
from setup_logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main(
    client: CogniteClient,
    fn_config: FunctionConfig,
    deploy_creds: DeployCredentials,
    schedule_config: SchedulesConfig,
) -> None:
    # Run static analysis / other checks and pre-deployment verifications:
    run_checks(fn_config)

    # Deploy code to Cognite Functions:
    fn = upload_and_create_function(client, fn_config)

    # Deploy schedules (if any):
    deploy_schedules(client, fn, schedule_config)

    # Return output parameter (GitHub magic syntax):
    print(f"::set-output name=function_external_id::{fn.external_id}")


if __name__ == "__main__":
    deploy_creds = DeployCredentials.from_envvars()
    client = deploy_creds.experimental_client

    # We have a short-cut for when we only need to delete a function:
    if delete_config := DeleteFunctionConfig.from_envvars():
        remove_function_with_file(client, delete_config.function_external_id)
    else:
        fn_config = FunctionConfig.from_envvars()
        schedule_config = SchedulesConfig.from_envvars()

        # Function Action OIDC, assemble!!
        main(client, fn_config, deploy_creds, schedule_config)
