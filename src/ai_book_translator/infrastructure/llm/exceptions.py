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

class PromptFixableError(LLMError):
    """Output error that may be fixable by changing prompt instructions."""
    pass


class ContentPolicyError(LLMError):
    """Model refused due to content policy; prompt change unlikely to help."""
    pass


class InternalCodeError(LLMError):
    """Internal/code failure — not an LLM issue, do not retry via LLM."""
    pass


# --- Error classification ---

class ErrorCategory:
    TRANSIENT_PROVIDER = "transient_provider_error"
    INVALID_MODEL_OUTPUT = "invalid_model_output"
    PROMPT_FIXABLE = "prompt_fixable_output_error"
    CONTENT_POLICY = "content_policy_or_refusal"
    INTERNAL_CODE = "internal_code_error"


def classify_error(exc: Exception) -> str:
    """Classify an exception into an error category for UI handling."""
    if isinstance(exc, (LLMTransientError, UploadFailedError)):
        return ErrorCategory.TRANSIENT_PROVIDER
    if isinstance(exc, LLMRefusalError):
        return ErrorCategory.CONTENT_POLICY
    if isinstance(exc, ContentPolicyError):
        return ErrorCategory.CONTENT_POLICY
    if isinstance(exc, PromptFixableError):
        return ErrorCategory.PROMPT_FIXABLE
    if isinstance(exc, LLMParsingError):
        return ErrorCategory.INVALID_MODEL_OUTPUT
    if isinstance(exc, InternalCodeError):
        return ErrorCategory.INTERNAL_CODE
    if isinstance(exc, LLMConfigurationError):
        return ErrorCategory.INTERNAL_CODE
    # Heuristic: RuntimeError with "empty translation" may be prompt-fixable
    msg = str(exc).lower()
    if "empty translation" in msg or "refused" in msg or "safety" in msg:
        return ErrorCategory.PROMPT_FIXABLE
    return ErrorCategory.INTERNAL_CODE


# Alias for backward compatibility
TransientLLMError = LLMTransientError
InvalidJSONError = LLMParsingError