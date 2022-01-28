import logging


class GitHubLogHandler(logging.StreamHandler):
    # Github only has debug, warning and error, and debug is not shown by default.
    # https://docs.github.com/en/free-pro-team@latest/actions/reference/workflow
    #   -commands-for-github-actions#setting-a-debug-message
    # We thus output INFO as WARNING and WARNING (and higher) as ERROR.

    @staticmethod
    def log_level_to_github(level: int) -> str:
        if level >= logging.WARNING:
            return "error"
        elif level > logging.DEBUG or level == logging.NOTSET:
            return "warning"
        else:
            return "debug"

    def format(self, record) -> str:
        msg = super().format(record)
        level = self.log_level_to_github(record.levelno)
        return f"::{level} file={record.filename},line={record.levelno}::{record.name}: {msg}"


def configure_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(GitHubLogHandler())
