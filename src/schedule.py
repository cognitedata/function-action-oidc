import logging
from typing import Dict, Optional

from cognite.experimental import CogniteClient
from cognite.experimental.data_classes import Function
from crontab import CronSlices
from pydantic import BaseModel, Field, validator

from configs import SchedulesConfig
from utils import NonEmptyString

logger = logging.getLogger(__name__)


class FunctionSchedule(BaseModel):
    class Config:
        allow_population_by_field_name = True

    name: NonEmptyString
    description: Optional[NonEmptyString]
    cron_expression: NonEmptyString = Field(alias="cron")
    data: Optional[Dict]

    @validator("cron_expression")
    def validate_cron(cls, cron):
        if not CronSlices.is_valid(cron):
            raise ValueError(f"Invalid cron expression: '{cron}'")
        return cron


def deploy_schedules(client: CogniteClient, fn: Function, schedule_config: SchedulesConfig):
    if not (schedules := schedule_config.schedules):
        logger.info("No schedules to attach to function!")
        return

    logger.info(f"Attaching {len(schedules)} schedule(s) to {fn.external_id} (by ID: {fn.id})")
    for s in schedules:
        client.functions.schedules.create(
            function_id=fn.id,
            client_credentials=schedule_config.credentials,
            **dict(s),
        )
        logger.info(f"- Schedule '{s.name}' with cron: '{s.cron_expression}' attached successfully!")
