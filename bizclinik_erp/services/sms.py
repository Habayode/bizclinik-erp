"""Provider-agnostic SMS gateway.

The app only talks to get_sms_provider().send(...). The DEFAULT provider is
``log`` — it records the message and sends nothing — so parent notifications
work with no gateway configured (no cost, demo-safe). Configure a real gateway
with SMS_PROVIDER=termii|twilio plus its credentials; until then SMS is logged.

Env:
  SMS_PROVIDER   termii | twilio | log   (default log)
  SMS_SENDER     alphanumeric sender id  (default "Trakit365")
  TERMII_API_KEY ...                      (Termii)
  TWILIO_SID / TWILIO_TOKEN / TWILIO_FROM (Twilio)
"""
from __future__ import annotations

import base64
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class SmsResult:
    ok: bool
    provider: str
    ref: Optional[str] = None
    error: Optional[str] = None
    transmitted: bool = True   # False for the log provider (recorded, not sent)


def _post(url: str, *, json_body: Optional[dict] = None,
          form: Optional[dict] = None, headers: Optional[dict] = None,
          timeout: int = 20) -> dict:
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    else:
        data = urllib.parse.urlencode(form or {}).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, method="POST", headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8") or "{}"
    try:
        return json.loads(raw)
    except ValueError:
        return {"raw": raw}


class SmsProvider:
    name = "base"

    def configured(self) -> bool:
        return False

    def send(self, *, to: str, message: str,
             sender: Optional[str] = None) -> SmsResult:
        raise NotImplementedError


class LogSms(SmsProvider):
    """Records the message but transmits nothing — the safe default."""
    name = "log"

    def configured(self) -> bool:
        return True

    def send(self, *, to: str, message: str, sender: Optional[str] = None) -> SmsResult:
        return SmsResult(ok=True, provider="log", ref="LOGGED", transmitted=False)


class TermiiSms(SmsProvider):
    name = "termii"
    BASE = os.environ.get("TERMII_BASE", "https://api.ng.termii.com").rstrip("/")

    def __init__(self):
        self.key = os.environ.get("TERMII_API_KEY", "").strip()
        self.sender = os.environ.get("SMS_SENDER", "Trakit365").strip()

    def configured(self) -> bool:
        return bool(self.key)

    def send(self, *, to: str, message: str, sender: Optional[str] = None) -> SmsResult:
        if not self.configured():
            return SmsResult(False, "termii", error="TERMII_API_KEY not set")
        try:
            data = _post(self.BASE + "/api/sms/send", json_body={
                "to": to, "from": (sender or self.sender), "sms": message,
                "type": "plain", "channel": "generic", "api_key": self.key})
            ref = str(data.get("message_id") or data.get("message") or "sent")
            return SmsResult(ok=True, provider="termii", ref=ref)
        except Exception as e:   # noqa: BLE001
            return SmsResult(False, "termii", error=str(e)[:200])


class TwilioSms(SmsProvider):
    name = "twilio"

    def __init__(self):
        self.sid = os.environ.get("TWILIO_SID", "").strip()
        self.token = os.environ.get("TWILIO_TOKEN", "").strip()
        self.from_ = os.environ.get("TWILIO_FROM", "").strip()

    def configured(self) -> bool:
        return bool(self.sid and self.token and self.from_)

    def send(self, *, to: str, message: str, sender: Optional[str] = None) -> SmsResult:
        if not self.configured():
            return SmsResult(False, "twilio", error="TWILIO_SID/TOKEN/FROM not set")
        try:
            auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
            data = _post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
                form={"To": to, "From": self.from_, "Body": message},
                headers={"Authorization": f"Basic {auth}"})
            return SmsResult(ok=True, provider="twilio", ref=str(data.get("sid") or "sent"))
        except Exception as e:   # noqa: BLE001
            return SmsResult(False, "twilio", error=str(e)[:200])


_PROVIDERS = {"log": LogSms, "termii": TermiiSms, "twilio": TwilioSms}


def get_sms_provider(name: Optional[str] = None) -> SmsProvider:
    key = (name or os.environ.get("SMS_PROVIDER") or "log").strip().lower()
    return _PROVIDERS.get(key, LogSms)()


def available_sms_providers() -> list[str]:
    return [k for k in _PROVIDERS if k != "log"]
