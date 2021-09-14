import logging

from cognite.experimental.data_classes import Function

from configs import SchedulesConfig

logger = logging.getLogger(__name__)


def deploy_schedules(fn: Function, schedule_config: SchedulesConfig):
    if not (schedules := schedule_config.schedules):
        logger.info("No schedules to attach to function!")
        return

    logger.info(f"Attaching {len(schedules)} schedule(s) to {fn.external_id} (by ID: {fn.id})")
    client = schedule_config.experimental_client
    for s in schedules:
        client.functions.schedules.create(
            function_id=fn.id,
            client_credentials=schedule_config.credentials,
            **dict(s),
        )
        logger.info(f"- Schedule '{s.name}' with cron: '{s.cron_expression}' attached successfully!")
