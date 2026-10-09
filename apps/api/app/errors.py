class AppError(Exception):
    status = 400
    code = "error"

    def __init__(self, message: str = "", code: str | None = None, status: int | None = None, **extra):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.extra = extra


class NotFound(AppError):
    status = 404
    code = "not_found"


class Forbidden(AppError):
    status = 403
    code = "forbidden"


class Conflict(AppError):
    status = 409
    code = "conflict"


class Invalid(AppError):
    status = 422
    code = "invalid"
