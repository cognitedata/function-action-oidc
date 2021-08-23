import logging
from typing import Dict, List, Optional

from cognite.experimental import CogniteClient
from cognite.experimental.data_classes import Function
from crontab import CronSlices
from pydantic import BaseModel, validator

from utils import NonEmptyString

logger = logging.getLogger(__name__)


class ScheduleConfig(BaseModel):
    name: NonEmptyString
    cron_expression: NonEmptyString
    data: Optional[Dict]

    @validator("cron_expression")
    def validate_cron(cls, cron):
        if not CronSlices.is_valid(cron):
            raise ValueError(f"Invalid cron expression: '{cron}'")
        return cron


def deploy_schedules(client: CogniteClient, fn: Function, schedules: List[ScheduleConfig]):
    if not schedules:
        logger.info("No schedules to attach!")
        return

    logger.info(f"Attaching {len(schedules)} schedule(s) to {fn.external_id} (by ID: {fn.id})")
    for s in schedules:
        client.functions.schedules.create(function_id=fn.id, **s.dict())
        logger.info(f"- Schedule '{s.name}' with cron: '{s.cron}' attached successfully!")


if __name__ == "__main__":
    s = ScheduleConfig(
        name="schedule name",
        cron_expression="* 10 * * *",
    )
    print(s)
    print(s.dump())
    print(dir(s))
