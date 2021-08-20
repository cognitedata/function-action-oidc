import logging
from typing import List

from cognite.experimental import CogniteClient
from cognite.experimental.data_classes import Function

from config import ScheduleConfig

logger = logging.getLogger(__name__)


def delete_function_schedules(client: CogniteClient, function_external_id: str):
    all_schedules = client.functions.schedules.list(function_external_id=function_external_id, limit=None)
    if all_schedules:
        for s in all_schedules:  # TODO: Experimental SDK does not support "delete multiple"
            client.functions.schedules.delete(s.id)
        logger.info(f"Deleted all ({len(all_schedules)}) existing schedule(s)!")
    else:
        logger.info("No existing schedule(s) to delete!")


def deploy_schedules(client: CogniteClient, function: Function, schedules: List[ScheduleConfig]):
    if not schedules:
        logger.info("No schedules to attach!")
        return

    logger.info(f"Attaching {len(schedules)} schedule(s) to {function.external_id}")
    for schedule in schedules:
        client.functions.schedules.create(
            function_external_id=function.external_id,
            cron_expression=schedule.cron,
            name=schedule.name,
            data=schedule.data,
        )
        logger.info(f"- Schedule '{schedule.name}' with cron: '{schedule.cron}' attached successfully!")
