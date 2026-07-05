from __future__ import annotations
import hashlib
import hmac
import time

import requests


class InstagramError(RuntimeError):
    pass


class InstagramClient:
    API = "https://graph.facebook.com/v19.0"

    def __init__(
        self,
        business_id: str,
        access_token: str,
        *,
        app_secret: str | None = None,
        poll_interval_seconds: float = 2.0,
        poll_timeout_seconds: float = 60.0,
        retry_wait_seconds: float = 5.0,
    ) -> None:
        self.business_id = business_id
        self.access_token = access_token
        self.app_secret = app_secret
        self.poll_interval = poll_interval_seconds
        self.poll_timeout = poll_timeout_seconds
        self.retry_wait = retry_wait_seconds

    def publish_image(self, image_url: str, caption: str) -> str:
        creation_id = self._create_container(image_url, caption)
        self._wait_container_ready(creation_id)
        return self._publish(creation_id)

    def _params(self, **extra: str) -> dict[str, str]:
        params = {"access_token": self.access_token, **extra}
        if self.app_secret:
            params["appsecret_proof"] = hmac.new(
                self.app_secret.encode("utf-8"),
                self.access_token.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
        return params

    def _create_container(self, image_url: str, caption: str) -> str:
        def call():
            return requests.post(
                f"{self.API}/{self.business_id}/media",
                params=self._params(image_url=image_url, caption=caption),
                timeout=30,
            )
        resp = self._with_retry(call, "create container")
        return resp.json()["id"]

    def _wait_container_ready(self, creation_id: str) -> None:
        deadline = time.monotonic() + self.poll_timeout
        while time.monotonic() < deadline:
            r = requests.get(
                f"{self.API}/{creation_id}",
                params=self._params(fields="status_code"),
                timeout=30,
            )
            r.raise_for_status()
            status = r.json().get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramError("container status ERROR")
            time.sleep(self.poll_interval)
        raise InstagramError("container status polling timed out")

    def _publish(self, creation_id: str) -> str:
        def call():
            return requests.post(
                f"{self.API}/{self.business_id}/media_publish",
                params=self._params(creation_id=creation_id),
                timeout=30,
            )
        resp = self._with_retry(call, "publish")
        return resp.json()["id"]

    def _with_retry(self, call, label: str):
        r = None
        for attempt in (1, 2):
            r = call()
            if r.status_code < 500:
                if r.status_code >= 400:
                    raise InstagramError(f"{label} failed {r.status_code}: {r.text}")
                return r
            if attempt == 1:
                time.sleep(self.retry_wait)
        raise InstagramError(
            f"{label} failed after retry: {r.status_code if r is not None else 'no response'}"
        )
