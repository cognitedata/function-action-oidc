import io
import logging
import os
from pathlib import Path
from zipfile import ZipFile

from cognite.client.data_classes import DataSet, FileMetadata
from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient
from retry import retry

from configs import FunctionConfig
from exceptions import FunctionDeployError
from utils import retrieve_dataset, temporary_chdir

logger = logging.getLogger(__name__)


def _write_files_to_zip_buffer(zf: ZipFile, directory: Path):
    for dirpath, _, files in os.walk(directory):
        zf.write(dirpath)
        for f in files:
            zf.write(Path(dirpath) / f)


@retry(exceptions=FunctionDeployError, tries=12, delay=2, jitter=2, max_delay=15)
def await_file_upload_status(client: CogniteClient, file_id: int):
    if not client.files.retrieve(file_id).uploaded:
        logger.info(f"- File (ID: {file_id}) not yet uploaded...")
        raise FunctionDeployError("File upload failed to reach 'uploaded=True' status")


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
    await_file_upload_status(client, file_meta.id)
    return file_meta


def zip_and_upload_folder(client: CogniteClient, fn_config: FunctionConfig, xid: str) -> int:
    logger.info(f"Uploading code from '{fn_config.function_folder}' to Files using external ID: '{xid}'")
    buf = io.BytesIO()  # TempDir, who needs that?! :rocket:
    with ZipFile(buf, mode="a") as zf:
        with temporary_chdir(fn_config.function_folder):
            _write_files_to_zip_buffer(zf, directory=Path())

        if (common_folder := fn_config.common_folder) is not None:
            with temporary_chdir(common_folder.parent):  # Note .parent
                logger.info(f"- Added common directory: '{common_folder}' to the file/function")
                _write_files_to_zip_buffer(zf, directory=common_folder)

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
    if (file_id := file_meta.id) is not None:
        logger.info(f"- File uploaded successfully ({xid})!")
        return file_id
    raise FunctionDeployError(f"Failed to upload file ({xid}) to CDF Files")


def delete_function_file(client: CogniteClient, xid: str):
    if (file_meta := client.files.retrieve(external_id=xid)) is None:
        logger.info(f"Unable to delete file! External ID: '{xid}' NOT found!")
        return

    logger.info(f"Deleting existing file '{xid}' (ID: {file_meta.id})")
    try:
        client.files.delete(external_id=xid)
        logger.info(f"- Delete of file '{xid}' successful!")
    except CogniteAPIError as err:
        logger.error(
            f"Unable to delete file, reason: {err!r}! Trying to ignore and continue as this action will "
            "overwrite the file later."
        )
