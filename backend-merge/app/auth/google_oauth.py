from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from app.config import settings


class GoogleTokenInvalid(Exception):
    pass


def verify_google_token(token: str) -> dict:
    try:
        idinfo = google_id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except ValueError as e:
        raise GoogleTokenInvalid(str(e)) from e

    if idinfo.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleTokenInvalid("Invalid token issuer")

    return {
        "google_id": idinfo["sub"],
        "email": idinfo["email"],
        "email_verified": idinfo.get("email_verified", False),
        "full_name": idinfo.get("name"),
    }
