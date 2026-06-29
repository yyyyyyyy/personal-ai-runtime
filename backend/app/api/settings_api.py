"""Settings API — runtime LLM and email configuration."""

import time

from fastapi import APIRouter, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel, field_validator

from app.core.agents.llm_router import llm_router
from app.core.runtime.runtime_config import PROVIDER_PRESETS, runtime_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LlmProviderInput(BaseModel):
    id: str
    name: str = ""
    type: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    enabled: bool = True


class UpdateLlmConfigRequest(BaseModel):
    default_provider: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    providers: list[LlmProviderInput] | None = None

    @field_validator("temperature")
    @classmethod
    def check_temperature(cls, value: float | None) -> float | None:
        if value is not None and (value < 0.0 or value > 2.0):
            raise ValueError("temperature must be between 0.0 and 2.0")
        return value

    @field_validator("max_tokens")
    @classmethod
    def check_max_tokens(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("max_tokens must be a positive integer")
        return value


class UpdateEmailConfigRequest(BaseModel):
    user: str = ""
    password: str = ""
    imap_host: str = "imap.gmail.com"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465


class TestEmailRequest(BaseModel):
    user: str | None = None
    password: str | None = None
    imap_host: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None


class TestLlmRequest(BaseModel):
    provider_id: str | None = None


def _llm_status_from_config(llm: dict) -> tuple[str, list[dict]]:
    """Derive default model and provider status from persisted config (not router cache)."""
    default_id = llm.get("default_provider", "deepseek")
    providers_public: list[dict] = []
    default_model = "deepseek-chat"

    for item in llm.get("providers", []):
        if not item.get("enabled", True):
            continue
        pid = item["id"]
        model = item.get("model", "")
        ptype = item.get("type", "openai_compatible")
        if ptype == "ollama":
            available = bool(item.get("base_url"))
        else:
            available = bool(item.get("has_api_key") or item.get("api_key"))
        is_default = pid == default_id
        if is_default and model:
            default_model = model
        providers_public.append({
            "name": pid,
            "model": model,
            "type": ptype,
            "is_default": is_default,
            "available": available,
        })

    return default_model, providers_public


@router.get("/llm")
async def get_llm_settings():
    """Get LLM configuration (secrets masked)."""
    llm = runtime_config.get_llm_config(masked=True)
    default_model, providers_public = _llm_status_from_config(llm)
    return {
        "config": llm,
        "default_model": default_model,
        "providers_status": providers_public,
        "presets": PROVIDER_PRESETS,
        "provider_types": {
            "openai_compatible": "OpenAI 兼容 API（DeepSeek / OpenAI / 代理）",
            "ollama": "Ollama 本地推理",
        },
    }


@router.put("/llm")
async def update_llm_settings(body: UpdateLlmConfigRequest):
    """Update LLM configuration and reload router."""
    payload = body.model_dump(exclude_none=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update")

    if body.providers is not None:
        ids = [p.id for p in body.providers]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=400, detail="Duplicate provider id")

    updated = runtime_config.update_llm_config(payload)
    llm_router.reload()

    if body.default_provider and body.default_provider not in {
        p["id"] for p in updated.get("providers", [])
    }:
        raise HTTPException(status_code=400, detail="default_provider not found in providers")

    default_model, providers_public = _llm_status_from_config(updated)

    return {
        "config": updated,
        "default_model": default_model,
        "providers_status": providers_public,
        "presets": PROVIDER_PRESETS,
        "provider_types": {
            "openai_compatible": "OpenAI 兼容 API（DeepSeek / OpenAI / 代理）",
            "ollama": "Ollama 本地推理",
        },
    }


@router.post("/llm/test")
async def test_llm_connection(body: TestLlmRequest | None = None):
    """Ping the default or specified LLM provider."""
    provider_id = (body.provider_id if body else None) or runtime_config.get_llm_config(masked=False).get(
        "default_provider", "deepseek"
    )
    providers = runtime_config.get_provider_credentials(provider_id)
    if not providers:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found or disabled")

    p = providers[0]
    api_key = p.get("api_key") or ("ollama" if p.get("type") == "ollama" else "")
    if not api_key and p.get("type") != "ollama":
        return {"ok": False, "provider": provider_id, "error": "API Key 未配置"}

    client = AsyncOpenAI(api_key=api_key, base_url=p.get("base_url", ""))
    start = time.perf_counter()
    try:
        await client.chat.completions.create(
            model=p.get("model", ""),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "ok": True,
            "provider": provider_id,
            "model": p.get("model"),
            "latency_ms": round(latency_ms, 1),
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": provider_id,
            "model": p.get("model"),
            "error": str(exc),
        }


@router.get("/email")
async def get_email_settings():
    """Get Gmail configuration (password masked)."""
    email_cfg = runtime_config.get_email_config(masked=True)
    return {
        "config": email_cfg,
        "provider": "gmail",
        "help": "使用 Gmail 应用专用密码（16 位），非登录密码。",
    }


@router.put("/email")
async def update_email_settings(body: UpdateEmailConfigRequest):
    """Update Gmail configuration."""
    updated = runtime_config.update_email_config(body.model_dump())
    return {"config": updated}


@router.post("/email/test")
async def test_email_connection(body: TestEmailRequest | None = None):
    """Test Gmail IMAP and SMTP connectivity.

    Accepts optional credentials in the body so the UI can test what the user
    just typed without saving first. Masked/empty fields fall back to the
    persisted config in the DB.
    """
    import imaplib
    import smtplib

    from app.core.runtime.runtime_config import _is_masked

    creds = runtime_config.get_email_credentials()
    user = (body.user if body and body.user else "") or creds.get("user", "")
    password = (body.password if body and body.password else "") or ""
    if not password or _is_masked(password):
        password = creds.get("password", "")
    if not user or not password:
        return {"ok": False, "imap_ok": False, "smtp_ok": False, "error": "邮箱或密码未配置"}

    imap_host = (body.imap_host if body and body.imap_host else None) or creds.get("imap_host", "imap.gmail.com")
    smtp_host = (body.smtp_host if body and body.smtp_host else None) or creds.get("smtp_host", "smtp.gmail.com")
    smtp_port = int((body.smtp_port if body and body.smtp_port else None) or creds.get("smtp_port", 465))

    imap_ok = False
    smtp_ok = False
    errors: list[str] = []

    try:
        mail = imaplib.IMAP4_SSL(imap_host, timeout=15)
        mail.login(user, password)
        mail.logout()
        imap_ok = True
    except Exception as exc:
        errors.append(f"IMAP: {exc}")

    try:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
        server.login(user, password)
        server.quit()
        smtp_ok = True
    except Exception as exc:
        errors.append(f"SMTP: {exc}")

    return {
        "ok": imap_ok and smtp_ok,
        "imap_ok": imap_ok,
        "smtp_ok": smtp_ok,
        "error": "; ".join(errors) if errors else None,
    }


# ── Prompt customization API ──────────────────────────────────────────────

class PromptConfig(BaseModel):
    identity: str | None = None
    coding_rules: str | None = None


@router.get("/prompt")
async def get_prompt_config():
    """Get current prompt configuration (defaults or user-customized)."""
    from app.chat.prompt_artifact import DEFAULT_CODING_RULES, DEFAULT_IDENTITY

    identity = runtime_config.get_prompt("identity") or DEFAULT_IDENTITY
    coding_rules = runtime_config.get_prompt("coding_rules") or DEFAULT_CODING_RULES

    return {
        "identity": identity,
        "coding_rules": coding_rules,
        "is_custom_identity": runtime_config.get_prompt("identity") is not None,
        "is_custom_coding_rules": runtime_config.get_prompt("coding_rules") is not None,
    }


@router.put("/prompt")
async def update_prompt_config(body: PromptConfig):
    """Update prompt configuration. Saves to app_settings and invalidates cache."""
    if body.identity is not None:
        content = body.identity.strip()
        if content:
            runtime_config.save_prompt("identity", content)
        else:
            runtime_config.save_prompt("identity", "")  # Reset to default

    if body.coding_rules is not None:
        content = body.coding_rules.strip()
        if content:
            runtime_config.save_prompt("coding_rules", content)
        else:
            runtime_config.save_prompt("coding_rules", "")

    # Also write to prompt files for persistence
    from pathlib import Path

    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    if body.identity is not None:
        (prompts_dir / "identity.md").write_text(body.identity, encoding="utf-8")

    if body.coding_rules is not None:
        (prompts_dir / "coding_rules.md").write_text(body.coding_rules, encoding="utf-8")

    return {"ok": True}


# ── Notification channel settings ──────────────────────────────────────────

class NotificationSettings(BaseModel):
    webhook_url: str = ""
    ntfy_topic: str = ""
    ntfy_server: str = "https://ntfy.sh"


@router.get("/notifications")
async def get_notification_settings():
    """Get current notification channel configuration."""
    from app.core.runtime.runtime_config import runtime_config

    data = runtime_config.get_prompt("notifications")
    if data:
        try:
            import json
            return json.loads(data)
        except Exception:
            pass
    return {"webhook_url": "", "ntfy_topic": "", "ntfy_server": "https://ntfy.sh"}


@router.put("/notifications")
async def update_notification_settings(body: NotificationSettings):
    """Update notification channel configuration."""
    from app.core.runtime.notification_channel import notification_router
    from app.core.runtime.runtime_config import runtime_config

    runtime_config.save_prompt("notifications", body.model_dump_json())

    # Apply settings immediately
    notification_router.configure(
        webhook_url=body.webhook_url,
        ntfy_topic=body.ntfy_topic,
        ntfy_server=body.ntfy_server,
    )

    return {"ok": True}
