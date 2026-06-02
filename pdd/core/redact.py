import re

# Robust patterns for redacting sensitive information
_PATTERNS = [
    # GitHub Tokens
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bgho_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bghu_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bghs_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"\bghr_[A-Za-z0-9]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    
    # Google API Keys
    (re.compile(r"\bAIza[0-9A-Za-z-_]{20,}\b"), "[REDACTED_GOOGLE_KEY]"),
    
    # OpenAI Keys
    (re.compile(r"\bsk-[0-9A-Za-z-_]{20,}\b"), "[REDACTED_OPENAI_KEY]"),
    
    # Anthropic Keys
    (re.compile(r"\bsk-ant-[0-9A-Za-z-_]{20,}\b"), "[REDACTED_ANTHROPIC_KEY]"),
    
    # Groq Keys
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"), "[REDACTED_GROQ_KEY]"),
    
    # xAI Keys
    (re.compile(r"\bxai-[A-Za-z0-9]{20,}\b"), "[REDACTED_XAI_KEY]"),
]

# Environment variable assignments (e.g., GH_TOKEN=...)
_ENV_VAR_RE = re.compile(
    r"\b(GITHUB_TOKEN|GH_TOKEN|OPENAI_API_KEY|GOOGLE_API_KEY|ANTHROPIC_API_KEY|GROQ_API_KEY|XAI_API_KEY|AWS_SECRET_ACCESS_KEY|PDD_AGENTIC_PROVIDER_KEY|CODE_GENERATOR_KEY|KEYRING_PASSWORD|SECRET|PASSWORD|TOKEN)\s*[:=]\s*([\"']?)([A-Za-z0-9\-_./+=]{8,})\2",
    re.IGNORECASE
)

# Bearer tokens
_BEARER_TOKEN_RE = re.compile(r"(Authorization\s*:\s*Bearer\s+)([A-Za-z0-9\-_./+=]{8,})", re.IGNORECASE)

# Generic secret labels
_GENERIC_SECRET_RE = re.compile(
    r"\b(api_key|secret|password|token|credential)s?\b\s*[:=]\s*([\"']?)([A-Za-z0-9\-_./+=]{8,})\2",
    re.IGNORECASE
)

def redact(text: str) -> str:
    """
    Redact sensitive information (API keys, tokens, secrets) from text.
    """
    if not text:
        return text
        
    redacted = text
    
    # 1. Apply specific service patterns
    for pattern, replacement in _PATTERNS:
        redacted = pattern.sub(replacement, redacted)
        
    # 2. Apply environment variable patterns
    redacted = _ENV_VAR_RE.sub(lambda m: f"{m.group(1)}={m.group(2)}[REDACTED]{m.group(2)}", redacted)
    
    # 3. Apply bearer token pattern
    redacted = _BEARER_TOKEN_RE.sub(lambda m: f"{m.group(1)}[REDACTED]", redacted)
    
    # 4. Apply generic secret patterns
    redacted = _GENERIC_SECRET_RE.sub(lambda m: f"{m.group(1)}: {m.group(2)}[REDACTED]{m.group(2)}", redacted)
    
    return redacted
