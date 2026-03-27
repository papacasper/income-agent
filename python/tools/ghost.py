"""
Ghost CMS integration for blog.papacasper.com
Publishes SEO articles + affiliate content via the Admin API.
Docs: https://ghost.org/docs/admin-api/
"""
import os
import time
import json
import hmac
import hashlib
import requests
from datetime import datetime, timezone


def _get_jwt() -> str:
    """Generate a short-lived JWT from the Ghost Admin API key."""
    key = os.getenv("GHOST_ADMIN_API_KEY", "")
    if ":" not in key:
        raise ValueError("GHOST_ADMIN_API_KEY must be in format id:secret")
    key_id, secret = key.split(":", 1)

    # Ghost uses HS256 JWT with 5-minute expiry
    import base64, struct

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "kid": key_id, "typ": "JWT"}).encode()).rstrip(b"=")
    now = int(time.time())
    payload = base64.urlsafe_b64encode(json.dumps({"iat": now, "exp": now + 300, "aud": "/admin/"}).encode()).rstrip(b"=")
    signing_input = header + b"." + payload
    sig = hmac.new(bytes.fromhex(secret), signing_input, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=")
    return (signing_input + b"." + sig_b64).decode()


def _headers() -> dict:
    return {
        "Authorization": f"Ghost {_get_jwt()}",
        "Content-Type": "application/json",
    }


def _base() -> str:
    url = os.getenv("GHOST_API_URL", "https://blog.papacasper.com")
    return url.rstrip("/") + "/ghost/api/admin"


def create_post(
    title: str,
    html: str,
    status: str = "published",   # "draft" or "published"
    tags: list[str] = None,
    meta_description: str = None,
    feature_image: str = None,
    canonical_url: str = None,
) -> dict:
    """Create (and optionally publish) a post on Ghost."""
    post: dict = {
        "title": title,
        "html": html,
        "status": status,
    }
    if tags:
        post["tags"] = [{"name": t} for t in tags]
    if meta_description:
        post["meta_description"] = meta_description
        post["og_description"] = meta_description
    if feature_image:
        post["feature_image"] = feature_image
    if canonical_url:
        post["canonical_url"] = canonical_url
    if status == "published":
        post["published_at"] = datetime.now(timezone.utc).isoformat()

    body = {"posts": [post]}
    r = requests.post(f"{_base()}/posts/", headers=_headers(), json=body, params={"source": "html"}, timeout=30)
    r.raise_for_status()
    created = r.json()["posts"][0]
    return {
        "id": created["id"],
        "title": created["title"],
        "url": created.get("url", ""),
        "status": created["status"],
        "slug": created.get("slug", ""),
    }


def list_posts(limit: int = 20, status: str = "all") -> list[dict]:
    r = requests.get(
        f"{_base()}/posts/",
        headers=_headers(),
        params={"limit": limit, "fields": "id,title,status,url,published_at", "filter": f"status:{status}" if status != "all" else None},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("posts", [])


def get_post_count() -> int:
    r = requests.get(f"{_base()}/posts/", headers=_headers(), params={"limit": 1}, timeout=10)
    r.raise_for_status()
    return r.json().get("meta", {}).get("pagination", {}).get("total", 0)


def ping_google_indexing(url: str) -> bool:
    """
    Submit a URL to Google Indexing API for fast crawling.
    Requires service account key file at GOOGLE_INDEXING_KEY_FILE.
    """
    key_file = os.getenv("GOOGLE_INDEXING_KEY_FILE")
    if not key_file or not os.path.exists(key_file):
        print(f"[Ghost] Google Indexing key not found at {key_file}, skipping")
        return False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        creds = service_account.Credentials.from_service_account_file(
            key_file,
            scopes=["https://www.googleapis.com/auth/indexing"],
        )
        service = build("indexing", "v3", credentials=creds)
        body = {"url": url, "type": "URL_UPDATED"}
        service.urlNotifications().publish(body=body).execute()
        print(f"[Ghost] Pinged Google Indexing: {url}")
        return True
    except Exception as e:
        print(f"[Ghost] Google Indexing failed: {e}")
        return False


def publish_article(
    title: str,
    html: str,
    tags: list[str] = None,
    meta_description: str = None,
    ping_google: bool = True,
) -> dict:
    """Publish an article and optionally ping Google for fast indexing."""
    post = create_post(
        title=title,
        html=html,
        status="published",
        tags=tags,
        meta_description=meta_description,
    )
    if ping_google and post.get("url"):
        ping_google_indexing(post["url"])
    return post
