import logging
from typing import Dict


class GitHubLogHandler(logging.StreamHandler):
    def __init__(self, stream=None):
        super(GitHubLogHandler, self).__init__(stream=stream)

    # https://docs.github.com/en/free-pro-team@latest/actions/reference/workflow-commands-for-github-actions#setting-a-debug-message
    def format(self, record):
        message = super(GitHubLogHandler, self).format(record)
        level_map: Dict = {
            logging.CRITICAL: "error",
            logging.ERROR: "error",
            logging.WARNING: "warning",
            logging.INFO: "warning",
            logging.DEBUG: "debug",
            logging.NOTSET: "warning",
        }
        return (
            f"::{level_map.get(record.levelno)} file={record.filename},line={record.levelno}::{record.name}: {message}"
        )
