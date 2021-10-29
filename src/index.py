import logging

from checks import run_checks
from cleanup import run_cleanup
from configs import DeleteFunctionConfig, DeployCredentials, FunctionConfig, RunConfig, SchedulesConfig
from orchestrator import remove_function_with_file, upload_and_create_function
from schedule import deploy_schedules
from setup_logging import configure_logging

configure_logging()
logger = logging.getLogger(__name__)


def main(config: RunConfig) -> None:
    # Run static analysis / other checks and pre-deployment verifications:
    run_checks(config.function)

    # Deploy code directory to Cognite Functions with schedules (if any)
    # and await successful deployment:
    deploy_client = config.deploy_creds.experimental_client
    fn = upload_and_create_function(deploy_client, config.function)
    deploy_schedules(fn, config.schedule)
    run_cleanup(fn, config.function)

    # Return output parameter (GitHub magic syntax):
    print(f"::set-output name=function_external_id::{fn.external_id}")


if __name__ == "__main__":
    deploy_creds = DeployCredentials.from_envvars()

    # We have a short-cut for when we only need to delete a function:
    if delete_config := DeleteFunctionConfig.from_envvars():
        remove_function_with_file(deploy_creds.experimental_client, delete_config.function_external_id)
    else:
        config = RunConfig(
            deploy_creds=deploy_creds,
            function=FunctionConfig.from_envvars(),
            schedule=SchedulesConfig.from_envvars(),
        )
        # Function Action OIDC, assemble!!
        main(config)
