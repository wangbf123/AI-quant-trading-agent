"""Map cloud-safe configuration names onto the retained upstream client."""
import os


def configure_upstream_environment():
    existing_url = os.getenv("AQR_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL", "")
    default_protocol = "anthropic" if not existing_url or "step_plan" in existing_url else "openai"
    os.environ.setdefault("AQR_LLM_PROTOCOL", default_protocol)
    if os.environ["AQR_LLM_PROTOCOL"] == "anthropic":
        os.environ.setdefault("AQR_LLM_BASE_URL", "https://api.stepfun.com/step_plan")
        os.environ.setdefault("AQR_LLM_MODEL", "step-5-preview")
    aliases = {
        "AQR_LLM_API_KEY": "OPENAI_API_KEY",
        "AQR_LLM_BASE_URL": "OPENAI_BASE_URL",
        "AQR_LLM_MODEL": "CHAT_MODEL",
    }
    for source, target in aliases.items():
        if os.getenv(source) and not os.getenv(target):
            os.environ[target] = os.environ[source]
    if os.getenv("AQR_LLM_MODEL"):
        os.environ.setdefault("REASONING_MODEL", os.environ["AQR_LLM_MODEL"])
    os.environ.setdefault("LOG_LLM_CHAT_CONTENT", "false")
    os.environ.setdefault("MAX_RETRY", "3")
    os.environ.setdefault("RETRY_WAIT_SECONDS", "2")
