import io
import logging
import time
from pathlib import Path
from zipfile import ZipFile

from cognite.client import CogniteClient
from cognite.client.data_classes import DataSet, FileMetadata
from cognite.client.exceptions import CogniteAPIError

from configs import FunctionConfig
from exceptions import FunctionDeployError
from utils import retrieve_dataset, retry_call

logger = logging.getLogger(__name__)


def _await_file_upload_status(client: CogniteClient, file_id: int, xid: str):
    # To be called from within a retry-block ignoring error until it passes or tries are spent
    if not client.files.retrieve(file_id).uploaded:
        logger.info(f"- File (ID: {file_id}) not yet uploaded...")
        raise FunctionDeployError(f"Failed to upload file ({xid}) to CDF Files")


def upload_zipped_code_to_files(
    client: CogniteClient,
    file_bytes: bytes,
    xid: str,
    ds: DataSet,
) -> FileMetadata:
    file_meta = client.files.upload_bytes(
        file_bytes,
        name=xid,
        external_id=xid,
        data_set_id=ds.id,
        overwrite=True,
    )
    # File upload can take some time... we are generous
    time.sleep(2)
    retry_call(
        _await_file_upload_status,
        (client, file_meta.id, xid),
        exceptions=FunctionDeployError,
        tries=12,
        delay=2,
        jitter=2,
        max_delay=15,
        logger=logger,
    )
    return file_meta


def zip_and_upload_folder(client: CogniteClient, fn_config: FunctionConfig, xid: str) -> int:
    logger.info(f"Uploading code from '{fn_config.function_folder}' to Files using external ID: '{xid}'")
    buf = io.BytesIO()  # TempDir, who needs that?! :rocket:
    with ZipFile(buf, mode="a") as zf:
        function_folder = Path(fn_config.function_folder)
        for filepath in function_folder.rglob("*"):
            dest_filepath = str(filepath).replace(str(function_folder), "")
            zf.write(filepath, dest_filepath)

        if fn_config.common_folder:
            common_folder = Path(fn_config.common_folder)
            for filepath in common_folder.rglob("*"):
                dest_filepath = f'common/{str(filepath).replace(str(common_folder), "")}'
                zf.write(filepath, dest_filepath)

    if (ds_id := fn_config.data_set_id) is not None:
        ds = retrieve_dataset(client, ds_id)
        logger.info(
            f"- Using dataset '{ds.external_id}' (ID: {ds_id}) to govern the file "
            f"(has write protection: {ds.write_protected})."
        )
    else:
        ds = DataSet(id=None)
        logger.info("- No dataset will be used to govern the function zip-file!")

    file_meta = upload_zipped_code_to_files(client, buf.getvalue(), xid, ds)
    logger.info(f"- File uploaded successfully ({xid})!")
    return file_meta.id


def delete_function_file(client: CogniteClient, xid: str):
    if (file_meta := client.files.retrieve(external_id=xid)) is None:
        logger.info(f"Unable to delete file! External ID: '{xid}' NOT found!")
        return

    logger.info(f"Deleting existing file '{xid}' (ID: {file_meta.id})")
    try:
        client.files.delete(external_id=xid)
        logger.info(f"- Delete of file '{xid}' successful!")
    except CogniteAPIError as e:
        reason = f"{type(e).__name__}({e})"  # 'CogniteAPIError' does not implement dunder repr...
        logger.error(
            "Unable to delete file! Trying to ignore and continue as this action will overwrite "
            f"the file later. Error message from the API: \n{reason}"
        )
