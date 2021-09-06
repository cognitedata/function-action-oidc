class MissingAclError(ValueError):
    pass


class FunctionDeployTimeout(RuntimeError):
    pass


class FunctionDeployError(RuntimeError):
    pass


class FunctionValidationError(Exception):
    pass
