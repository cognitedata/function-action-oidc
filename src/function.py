import logging
import time

from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient

from utils import create_zipfile_name

logger = logging.getLogger(__name__)


class FunctionStatus:
    # Not an exhaustive list, only what's needed:
    FAILED = "Failed"
    READY = "Ready"


def delete_single_cognite_function(fn_xid: str, client: CogniteClient):
    delete_function(client, fn_xid)
    delete_function_file(client, create_zipfile_name(fn_xid))
    time.sleep(3)


def delete_function(client: CogniteClient, xid: str):
    if (fn := client.functions.retrieve(external_id=xid)) is not None:
        logger.info(f"Deleting existing function '{xid}' (ID: {fn.id})")
        client.functions.delete(external_id=xid)
        logger.info(f"- Delete of function '{xid}' successful!")
    else:
        logger.info(f"Unable to delete function! External ID: '{xid}' NOT found!")


def delete_function_file(client: CogniteClient, xid: str):
    if (file_meta := client.files.retrieve(external_id=xid)) is None:
        logger.info(f"Unable to delete file! External ID: '{xid}' NOT found!")
        return

    logger.info(f"Deleting existing file '{xid}' (ID: {file_meta.id})")
    try:
        client.files.delete(external_id=xid)
        logger.info(f"- Delete of file '{xid}' successful!")
    except CogniteAPIError:
        if file_meta.data_set_id is None:
            raise  # File is not protected by dataset, so we re-raise immediately
        logger.error(
            f"Unable to delete file! It is governed by data set with ID: {file_meta.data_set_id}. "
            "Make sure your deployment credentials have write/owner access (see README.md in "
            "function-action repo). Trying to ignore and continue as this workflow will "
            "overwrite the file later."
        )
