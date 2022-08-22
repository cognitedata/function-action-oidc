import logging
import time

from cognite.client import CogniteClient
from cognite.client.data_classes import Function
from retry import retry  # type: ignore

from configs import FunctionConfig
from exceptions import FunctionDeployError
from function import await_function_deployment, create_function, delete_function
from function_file import delete_function_file, zip_and_upload_folder
from utils import create_zipfile_name

logger = logging.getLogger(__name__)


def remove_function_with_file(client: CogniteClient, fn_xid: str):
    delete_function(client, fn_xid)
    delete_function_file(client, create_zipfile_name(fn_xid))
    time.sleep(3)  # Tiny breather


@retry(exceptions=FunctionDeployError, tries=3, delay=5, backoff=2)
def upload_and_create_function(client: CogniteClient, fn_config: FunctionConfig) -> Function:
    fn_xid = fn_config.function_external_id
    remove_function_with_file(client, fn_xid)
    file_xid = create_zipfile_name(fn_xid)

    file_id = zip_and_upload_folder(client, fn_config, file_xid)
    fn_under_deployment = create_function(client, file_id, fn_config)
    return await_function_deployment(fn_under_deployment, fn_config.function_deploy_timeout)
