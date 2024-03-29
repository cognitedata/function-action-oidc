import logging
import time
from contextlib import suppress

from cognite.client import CogniteClient
from cognite.client.data_classes import Function
from cognite.client.exceptions import CogniteAPIError, CogniteNotFoundError
from humanize.time import precisedelta

from configs import FunctionConfig
from exceptions import FunctionDeployError, FunctionDeployTimeout

logger = logging.getLogger(__name__)


class FunctionStatus:
    # Not an exhaustive list, only what's needed:
    FAILED = "Failed"
    READY = "Ready"


def await_function_deployment(fn: Function, function_deploy_timeout: int) -> Function:
    deploy_time = time.time()
    next_info_log = deploy_time + 90  # Log progress every 90 sec
    while (now := time.time()) <= deploy_time + function_deploy_timeout:
        elapsed_time = precisedelta(now - deploy_time)
        if fn.status == FunctionStatus.READY:
            logger.info(f"Function deployment successful! Deployment took {elapsed_time}")
            return fn

        elif fn.status == FunctionStatus.FAILED:
            err_msg = f"{fn.error['message']}. Trace:\n{fn.error['trace']}"
            logger.error(f"Deployment failed after {elapsed_time}! API returned error: {err_msg}")
            raise FunctionDeployError(err_msg)

        elif now > next_info_log:
            next_info_log += 90
            logger.info(f"- Deployment in progress, current status: '{fn.status}', time elapsed: {elapsed_time}")

        time.sleep(5)
        fn.update()

    # Attempt to cancel deployment because of timeout:
    with suppress(CogniteAPIError, CogniteNotFoundError):
        fn._cognite_client.functions.delete(id=fn.id)
    timeout_msg = (
        f"Function {fn.external_id} (ID: {fn.id}) did not deploy within the given timeout-limit: "
        f"{function_deploy_timeout} sec, and was (attempted) cancelled. You can change this timeout setting "
        "by passing the parameter 'function_deploy_timeout' to this Github Action!"
    )
    logger.error(timeout_msg)
    raise FunctionDeployTimeout(timeout_msg)


def create_function(client: CogniteClient, file_id: int, fn_config: FunctionConfig) -> Function:
    fn_xid = fn_config.function_external_id
    logger.info(f"Trying to create function '{fn_xid}'...")
    if secrets := fn_config.function_secrets:
        logger.info(f"...with {len(secrets)} extra secret(s) named: {list(secrets)}")
    else:
        logger.info("...with no extra secrets")

    for n_try in range(1, 4):
        try:
            fn = client.functions.create(file_id=file_id, **fn_config.create_fn_params())
            logger.info(f"Function '{fn_xid}' created and queued for deployment! (ID: {fn.id}).")
            return fn
        except CogniteAPIError as e:
            if e.code in {503}:
                logger.exception(f"Create function failed, will retry (attempt #{n_try}). Exception:")
                time.sleep(n_try**2)  # Exp. backoff
                continue
            raise


def delete_function(client: CogniteClient, xid: str):
    if (fn := client.functions.retrieve(external_id=xid)) is not None:
        logger.info(f"Deleting existing function '{xid}' (ID: {fn.id})")
        client.functions.delete(external_id=xid)
        logger.info(f"- Delete of function '{xid}' successful!")
    else:
        logger.info(f"Unable to delete function! External ID: '{xid}' NOT found!")
