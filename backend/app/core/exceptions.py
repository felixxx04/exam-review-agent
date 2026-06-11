class AppException(Exception):
    def __init__(self, message: str, code: str = "APP_ERROR"):
        self.message = message
        self.code = code


class InsufficientMaterialError(AppException):
    def __init__(self, message: str = "上传的资料中未找到相关内容"):
        super().__init__(message, "INSUFFICIENT_MATERIAL")


class LLMProviderError(AppException):
    def __init__(self, provider: str, message: str = ""):
        super().__init__(
            f"LLM provider {provider} error: {message}", "LLM_PROVIDER_ERROR"
        )


class FileParsingError(AppException):
    def __init__(self, filename: str, message: str = ""):
        super().__init__(
            f"Failed to parse {filename}: {message}", "FILE_PARSING_ERROR"
        )


class RateLimitExceededError(AppException):
    def __init__(self):
        super().__init__("Rate limit exceeded", "RATE_LIMIT_EXCEEDED")
