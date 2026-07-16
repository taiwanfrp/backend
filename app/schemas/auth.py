from app.schemas.common import ErrorResponse


# Discord callback
DISCORD_CALLBACK_DOC = {
    400: {
        "model": ErrorResponse,
        "description": "",
        "content": {
            "application/json": {
                "examples": {
                    "invalid_oauth_state": {
                        "summary": "Invalid or missing OAuth state",
                        "value": {"detail": "Invalid OAuth state"},
                    },
                    "missing_authorization_code": {
                        "summary": "Missing authorization code",
                        "value": {"detail": "Missing authorization code"},
                    },
                    "failed_token_exchange": {
                        "summary": "Failed token exchange",
                        "value": {"detail": "Failed to exchange code for token"},
                    },
                    "no_access_token": {
                        "summary": "No access token",
                        "value": {"detail": "No access token received"},
                    },
                    "failed_user_info_fetch": {
                        "summary": "Failed user info fetch",
                        "value": {"detail": "Failed to fetch user info"},
                    },
                }
            }
        },
    }
}
