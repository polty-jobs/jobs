import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from src.instagram import InstagramClient, InstagramError


@responses.activate
def test_appsecret_proof_added_when_secret_provided():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    responses.add(responses.GET,
                  "https://graph.facebook.com/v19.0/C1",
                  json={"status_code": "FINISHED"}, status=200)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
                  json={"id": "P1"}, status=200)

    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN", app_secret="SECRET")
    c.publish_image("https://x/img.png", "hi")

    expected = hmac.new(b"SECRET", b"TOKEN", hashlib.sha256).hexdigest()
    for call in responses.calls:
        q = parse_qs(urlparse(call.request.url).query)
        assert q.get("appsecret_proof") == [expected], f"missing proof on {call.request.url}"


@responses.activate
def test_appsecret_proof_omitted_when_no_secret():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    responses.add(responses.GET,
                  "https://graph.facebook.com/v19.0/C1",
                  json={"status_code": "FINISHED"}, status=200)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
                  json={"id": "P1"}, status=200)

    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN")
    c.publish_image("https://x/img.png", "hi")

    for call in responses.calls:
        q = parse_qs(urlparse(call.request.url).query)
        assert "appsecret_proof" not in q


@responses.activate
def test_publish_flow_calls_container_then_publish():
    responses.add(
        responses.POST,
        "https://graph.facebook.com/v19.0/BIZ_ID/media",
        json={"id": "CREATION_123"}, status=200,
    )
    responses.add(
        responses.GET,
        "https://graph.facebook.com/v19.0/CREATION_123",
        json={"status_code": "FINISHED"}, status=200,
    )
    responses.add(
        responses.POST,
        "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
        json={"id": "POST_999"}, status=200,
    )

    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN")
    post_id = c.publish_image(image_url="https://x/img.png", caption="hi")
    assert post_id == "POST_999"


@responses.activate
def test_publish_retries_on_5xx_then_succeeds():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  status=502)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    responses.add(responses.GET,
                  "https://graph.facebook.com/v19.0/C1",
                  json={"status_code": "FINISHED"}, status=200)
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media_publish",
                  json={"id": "P1"}, status=200)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN", retry_wait_seconds=0)
    assert c.publish_image("https://x/img.png", "hi") == "P1"


@responses.activate
def test_container_status_polling_times_out_raises():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    for _ in range(40):
        responses.add(responses.GET,
                      "https://graph.facebook.com/v19.0/C1",
                      json={"status_code": "IN_PROGRESS"}, status=200)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN",
                        poll_interval_seconds=0, poll_timeout_seconds=1)
    with pytest.raises(InstagramError, match="container.*timed out"):
        c.publish_image("https://x/img.png", "hi")


@responses.activate
def test_container_error_status_raises():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"id": "C1"}, status=200)
    responses.add(responses.GET,
                  "https://graph.facebook.com/v19.0/C1",
                  json={"status_code": "ERROR"}, status=200)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN",
                        poll_interval_seconds=0)
    with pytest.raises(InstagramError, match="ERROR"):
        c.publish_image("https://x/img.png", "hi")


@responses.activate
def test_4xx_raises_immediately_no_retry():
    responses.add(responses.POST,
                  "https://graph.facebook.com/v19.0/BIZ_ID/media",
                  json={"error": {"message": "bad url"}}, status=400)
    c = InstagramClient(business_id="BIZ_ID", access_token="TOKEN")
    with pytest.raises(InstagramError, match="400"):
        c.publish_image("https://x/img.png", "hi")
