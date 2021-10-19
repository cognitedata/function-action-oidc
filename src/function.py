import logging
import time

from cognite.experimental import CogniteClient
from cognite.experimental.data_classes import Function
from humanize.time import precisedelta

from configs import FunctionConfig
from exceptions import FunctionDeployError, FunctionDeployTimeout

logger = logging.getLogger(__name__)


WAIT_TIME_SEC = 1500  # 25 minutes


class FunctionStatus:
    # Not an exhaustive list, only what's needed:
    FAILED = "Failed"
    READY = "Ready"


def await_function_deployment(client: CogniteClient, fn: Function, wait_time_sec: int = WAIT_TIME_SEC) -> Function:
    deploy_time = time.time()
    next_info_log = deploy_time + 90  # Log progress every 90 sec
    while (now := time.time()) <= deploy_time + wait_time_sec:
        elapsed_time = precisedelta(now - deploy_time)
        if fn.status == FunctionStatus.READY:
            logger.info(f"Function deployment successful! Deployment took {elapsed_time}")
            return fn

        elif fn.status == FunctionStatus.FAILED:
            err_msg = f"Error message: {fn.error['message']}.\nTrace: {fn.error['trace']}"
            logger.warning(f"Deployment failed after {elapsed_time}! {err_msg}")
            raise FunctionDeployError(err_msg)

        elif now > next_info_log:
            next_info_log += 90
            logger.info(f"- Deployment in progress, time elapsed: {elapsed_time}")

        time.sleep(5)
        fn.update()

    err = f"Function {fn.external_id} (ID: {fn.id}) did not deploy within {precisedelta(wait_time_sec)}."
    logger.error(err)
    raise FunctionDeployTimeout(err)


def create_function(client: CogniteClient, file_id: int, fn_config: FunctionConfig) -> Function:
    fn_xid = fn_config.function_external_id
    logger.info(f"Trying to create function '{fn_xid}'...")
    if secrets := fn_config.function_secrets:
        logger.info(f"...with {len(secrets)} extra secret(s) named: {list(secrets)}")
    else:
        logger.info("...with no extra secrets")

    fn = client.functions.create(file_id=file_id, **fn_config.create_fn_params())
    logging.info(f"Function '{fn_xid}' created successfully! (ID: {fn.id}).")
    return fn


def delete_function(client: CogniteClient, xid: str):
    if (fn := client.functions.retrieve(external_id=xid)) is not None:
        logger.info(f"Deleting existing function '{xid}' (ID: {fn.id})")
        client.functions.delete(external_id=xid)
        logger.info(f"- Delete of function '{xid}' successful!")
    else:
        logger.info(f"Unable to delete function! External ID: '{xid}' NOT found!")
