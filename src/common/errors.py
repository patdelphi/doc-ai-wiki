"""程序说明：定义系统级异常类型，并统一错误码。"""

from __future__ import annotations


class AppError(Exception):
    """应用基础异常。"""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "INTERNAL_ERROR",
        details: dict | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code


class ValidationAppError(AppError):
    """输入校验失败异常。"""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details=details,
            status_code=422,
        )


class DatabaseAppError(AppError):
    """数据库异常。"""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code="DATABASE_ERROR",
            details=details,
            status_code=500,
        )


class NotFoundAppError(AppError):
    """资源不存在异常。"""

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(
            message,
            error_code="NOT_FOUND",
            details=details,
            status_code=404,
        )
