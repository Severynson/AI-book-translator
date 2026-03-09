class LLMError(Exception):
    """Base class for all LLM-related errors."""
    pass

class LLMTransientError(LLMError):
    """Temporary errors (timeouts, rate limits, 5xx). Retry recommended."""
    pass

class LLMConfigurationError(LLMError):
    """Invalid API key, bad model name, or misconfiguration. Do not retry."""
    pass

class LLMRefusalError(LLMError):
    """Model refused to generate content (safety filter, policy violation)."""
    pass

class LLMParsingError(LLMError):
    """Model output could not be parsed (e.g. invalid JSON)."""
    pass

class UploadNotSupportedError(LLMError):
    """Provider does not support document upload."""
    pass

class UploadFailedError(LLMError):
    """Document upload failed."""
    pass

class DocumentReadError(LLMError):
    """Failed to read document content."""
    pass

class SchemaValidationError(LLMError):
    """Metadata does not match required schema."""
    pass

# Alias for backward compatibility if needed, or deprecate
TransientLLMError = LLMTransientError
InvalidJSONError = LLMParsingError