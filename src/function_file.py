import io
import logging
import os
from pathlib import Path
from zipfile import ZipFile

from cognite.client.data_classes import DataSet, FileMetadata
from cognite.client.exceptions import CogniteAPIError
from cognite.experimental import CogniteClient

from configs import FunctionConfig
from exceptions import FunctionDeployError
from utils import retrieve_dataset, temporary_chdir

logger = logging.getLogger(__name__)


def _write_files_to_zip_buffer(zf: ZipFile, directory: Path):
    for dirpath, _, files in os.walk(directory):
        zf.write(dirpath)
        for f in files:
            zf.write(Path(dirpath) / f)


def upload_zipped_code_to_files(
    client: CogniteClient,
    file_bytes: bytes,
    name: str,
    ds: DataSet,
) -> FileMetadata:
    try:
        return client.files.upload_bytes(
            file_bytes,
            name=name,
            external_id=name,
            data_set_id=ds.id,
            overwrite=True,
        )
    except CogniteAPIError as exc:
        if ds.id is None:
            # Error is not dataset related, so we immediately re-raise
            raise
        if ds.write_protected:
            err_msg = (
                "Unable to upload file to WRITE-PROTECTED dataset: Deployment credentials MUST have capability "
                "'dataset:OWNER' (and have 'files:WRITE' scoped to the same dataset OR all files)."
            )
        else:
            err_msg = (
                "Unable to upload file to dataset: Deployment credentials must have capability "
                "'files:WRITE' scoped to the same dataset OR all files."
            )
        logger.error(err_msg)
        raise CogniteAPIError(err_msg, exc.code, exc.x_request_id) from None


def zip_and_upload_folder(client: CogniteClient, fn_config: FunctionConfig, name: str) -> int:
    logger.info(f"Uploading code from '{fn_config.function_folder}' to '{name}'")
    buf = io.BytesIO()  # TempDir, who needs that?! :rocket:
    with ZipFile(buf, mode="a") as zf:
        with temporary_chdir(fn_config.function_folder):
            _write_files_to_zip_buffer(zf, directory=Path())

        if (common_folder := fn_config.common_folder) is not None:
            with temporary_chdir(common_folder.parent):  # Note .parent
                logger.info(f"- Added common directory: '{common_folder}' to the file/function")
                _write_files_to_zip_buffer(zf, directory=common_folder)

    if (ds_xid := fn_config.data_set_external_id) is not None:
        ds = retrieve_dataset(client, ds_xid)
        logger.info(
            f"- Using dataset '{ds.external_id}' to govern the file (has write protection: {ds.write_protected})."
        )
    else:
        ds = DataSet(id=None)
        logger.info("- No dataset will be used to govern the function zip-file!")

    file_meta = upload_zipped_code_to_files(client, buf.getvalue(), name, ds)
    if (file_id := file_meta.id) is not None:
        logger.info(f"- File uploaded successfully ({name})!")
        return file_id
    raise FunctionDeployError(f"Failed to upload file ({name}) to CDF Files")


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
