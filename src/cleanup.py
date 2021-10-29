import logging

from cognite.client.exceptions import CogniteAPIError
from cognite.experimental.data_classes import Function

from configs import FunctionConfig
from utils import create_zipfile_name

logger = logging.getLogger(__name__)


def run_cleanup(fn: Function, fn_config: FunctionConfig) -> None:
    if not fn_config.post_deploy_cleanup:
        logger.info("Skipping post-deployment cleanup!")
        return

    logger.info("Running post-deployment cleanup!")
    _delete_code_file(fn)


def _delete_code_file(fn: Function) -> None:
    file_xid = create_zipfile_name(fn.external_id)
    try:
        fn._cognite_client.files.delete(external_id=file_xid)
        logger.info(f"- Code file object deleted! (XID: {file_xid})")
    except CogniteAPIError:
        logger.info(f"- Unable to delete file object with external ID: {file_xid})")
