class LLMError(Exception):
    pass

class UploadNotSupportedError(LLMError):
    pass

class UploadFailedError(LLMError):
    pass

class TransientLLMError(LLMError):
    pass

class InvalidJSONError(LLMError):
    pass

class SchemaValidationError(LLMError):
    pass

class DocumentReadError(Exception):
    pass
