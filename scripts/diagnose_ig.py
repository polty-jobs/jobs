"""Standalone diagnostic for the Instagram Graph API setup.

Usage:
    export IG_ACCESS_TOKEN=...
    export IG_BUSINESS_ACCOUNT_ID=...
    export IG_APP_SECRET=...
    python scripts/diagnose_ig.py

Prints exactly what's wrong. No secrets are written to stdout.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import sys

import requests

API = "https://graph.facebook.com/v19.0"


def _proof(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def _mask(s: str, keep: int = 4) -> str:
    return "***" if not s or len(s) <= keep else s[:keep] + "…" + s[-keep:]


def _get(url: str, params: dict) -> tuple[int, dict]:
    r = requests.get(url, params=params, timeout=15)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:400]}


def main() -> int:
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    biz_id = os.environ.get("IG_BUSINESS_ACCOUNT_ID", "").strip()
    secret = os.environ.get("IG_APP_SECRET", "").strip()

    print("== Environment ==")
    print(f"  IG_ACCESS_TOKEN:        {'set (' + _mask(token) + ')' if token else 'MISSING'}")
    print(f"  IG_BUSINESS_ACCOUNT_ID: {biz_id or 'MISSING'}")
    print(f"  IG_APP_SECRET:          {'set (' + _mask(secret) + ')' if secret else 'MISSING'}")
    if not (token and biz_id and secret):
        print("\nSet the three env vars first.")
        return 1

    proof = _proof(token, secret)
    params = {"access_token": token, "appsecret_proof": proof}

    # 1) Scopes on the token
    print("\n== [1/4] Token scopes ==")
    status, body = _get(
        f"{API}/debug_token",
        {"input_token": token, "access_token": token, "appsecret_proof": proof},
    )
    scopes = body.get("data", {}).get("scopes") or []
    app_id = body.get("data", {}).get("app_id")
    valid = body.get("data", {}).get("is_valid")
    expires = body.get("data", {}).get("data_access_expires_at") or body.get("data", {}).get("expires_at")
    print(f"  status={status}  app_id={app_id}  is_valid={valid}  expires_at={expires}")
    if not valid:
        print(f"  ERROR: token not valid. Body: {json.dumps(body, ensure_ascii=False)[:400]}")
        return 2
    required = {"instagram_basic", "instagram_content_publish", "pages_show_list", "pages_read_engagement"}
    missing = required - set(scopes)
    print(f"  scopes present: {sorted(scopes)}")
    if missing:
        print(f"  ❌ MISSING SCOPES: {sorted(missing)}")
        print("     → Regenerate token in Graph API Explorer with these scopes checked.")
    else:
        print("  ✅ All required scopes present.")

    # 2) Pages this token can see
    print("\n== [2/4] Facebook pages this token can access ==")
    status, body = _get(f"{API}/me/accounts",
                        {**params, "fields": "id,name,instagram_business_account{id,username}"})
    pages = body.get("data") or []
    print(f"  status={status}  page_count={len(pages)}")
    for p in pages:
        ig = p.get("instagram_business_account") or {}
        print(f"    - page id={p.get('id')} name={p.get('name')!r} "
              f"→ ig id={ig.get('id') or '(none)'} username={ig.get('username') or '(none)'}")
    if not pages:
        print("  ❌ No pages returned. Token was likely issued for the wrong user, "
              "or the FB Page isn't connected to your app.")

    # 3) Does the configured IG_BUSINESS_ACCOUNT_ID actually match a known IG business account?
    print("\n== [3/4] IG_BUSINESS_ACCOUNT_ID check ==")
    ig_ids = [(p.get("id"), (p.get("instagram_business_account") or {}).get("id"),
               (p.get("instagram_business_account") or {}).get("username")) for p in pages]
    match = [row for row in ig_ids if row[1] == biz_id]
    if match:
        page_id, ig_id, username = match[0]
        print(f"  ✅ Matches IG @{username} (id={ig_id}) attached to page {page_id}")
    else:
        print(f"  ❌ IG_BUSINESS_ACCOUNT_ID={biz_id} is NOT in the list above.")
        for pid, iid, uname in ig_ids:
            hint = "  (this IG business id looks like the correct one)" if iid else ""
            print(f"     candidate: page {pid} → ig {iid} @{uname or '?'}{hint}")

    # 4) Direct fetch of the biz id
    print("\n== [4/4] Direct fetch of biz id ==")
    status, body = _get(f"{API}/{biz_id}", {**params, "fields": "id,username,name"})
    print(f"  status={status}  body={json.dumps(body, ensure_ascii=False)[:400]}")
    if status == 200 and body.get("username"):
        print(f"  ✅ Reachable. Username: @{body['username']}")
    else:
        print("  ❌ Not reachable with this token.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
