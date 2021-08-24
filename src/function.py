import logging
import time

from cognite.experimental import CogniteClient
from cognite.experimental.data_classes import Function
from humanize.time import precisedelta

from configs import FunctionConfig
from exceptions import FunctionDeployError, FunctionDeployTimeout

logger = logging.getLogger(__name__)


class FunctionStatus:
    # Not an exhaustive list, only what's needed:
    FAILED = "Failed"
    READY = "Ready"


def await_function_deployment(client: CogniteClient, fn: Function, wait_time_sec: int = 1200) -> Function:
    t0 = time.time()
    while time.time() <= t0 + wait_time_sec:
        if fn.status == FunctionStatus.READY:
            logger.info(f"Function deployment successful! Deployment took {precisedelta(time.time()-t0)}")
            return fn

        elif fn.status == FunctionStatus.FAILED:
            err_msg = f"Error message: {fn.error['message']}.\nTrace: {fn.error['trace']}"
            logger.warning(f"Deployment failed after {precisedelta(time.time()-t0)}! {err_msg}")
            raise FunctionDeployError(err_msg)

        time.sleep(5)
        fn.update()

    err = f"Function {fn.external_id} (ID: {fn.id}) did not deploy within {precisedelta(wait_time_sec)}."
    logger.error(err)
    raise FunctionDeployTimeout(err)


def create_function_and_wait(client: CogniteClient, file_id: int, fn_config: FunctionConfig) -> Function:
    fn_xid = fn_config.external_id
    logger.info(f"Trying to create function '{fn_xid}'...")
    if secrets := fn_config.secrets:
        logger.info(f"- With {len(secrets)} extra secret(s) named: {list(secrets)}")
    else:
        logger.info("- With no extra secrets")
    fn = client.functions.create(
        name=fn_xid,
        external_id=fn_xid,
        file_id=file_id,
        function_path=fn_config.function_file,
        secrets=secrets,
        owner=fn_config.owner,
        **fn_config.get_memory_and_cpu(),  # Only pass mem/cpu if set to not overwrite defaults
    )
    logging.info(f"Function '{fn_xid}' created (ID: {fn.id}). Waiting for deployment...")
    return await_function_deployment(client, fn)


def delete_function(client: CogniteClient, xid: str):
    if (fn := client.functions.retrieve(external_id=xid)) is not None:
        logger.info(f"Deleting existing function '{xid}' (ID: {fn.id})")
        client.functions.delete(external_id=xid)
        logger.info(f"- Delete of function '{xid}' successful!")
    else:
        logger.info(f"Unable to delete function! External ID: '{xid}' NOT found!")
