"""Google OAuth router with request-aware redirect_uri (Vite host/port)."""

from __future__ import annotations

import secrets
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from httpx_oauth.oauth2 import OAuth2Token

from fastapi_users import models
from fastapi_users.authentication import AuthenticationBackend, Strategy
from fastapi_users.exceptions import UserAlreadyExists
from fastapi_users.jwt import SecretType, decode_jwt
from fastapi_users.manager import BaseUserManager, UserManagerDependency
from fastapi_users.router.common import ErrorCode, ErrorModel
from fastapi_users.router.oauth import (
    CSRF_TOKEN_COOKIE_NAME,
    CSRF_TOKEN_KEY,
    generate_csrf_token,
    generate_state_token,
    OAuth2AuthorizeResponse,
    STATE_TOKEN_AUDIENCE,
)

from app.shared.oauth_redirect import (
    oauth_callback_redirect_uri,
    RequestAwareOAuth2AuthorizeCallback,
)


def get_google_oauth_router(
    oauth_client,
    backend: AuthenticationBackend[models.UP, models.ID],
    get_user_manager: UserManagerDependency[models.UP, models.ID],
    state_secret: SecretType,
    associate_by_email: bool = False,
    is_verified_by_default: bool = False,
    *,
    csrf_token_cookie_name: str = CSRF_TOKEN_COOKIE_NAME,
    csrf_token_cookie_path: str = "/",
    csrf_token_cookie_domain: str | None = None,
    csrf_token_cookie_secure: bool = True,
    csrf_token_cookie_httponly: bool = True,
    csrf_token_cookie_samesite: Literal["lax", "strict", "none"] = "lax",
) -> APIRouter:
    router = APIRouter()
    callback_route_name = f"oauth:{oauth_client.name}.{backend.name}.callback"
    oauth2_authorize_callback = RequestAwareOAuth2AuthorizeCallback(
        oauth_client,
        redirect_url=oauth_callback_redirect_uri(),
    )

    @router.get(
        "/authorize",
        name=f"oauth:{oauth_client.name}.{backend.name}.authorize",
        response_model=OAuth2AuthorizeResponse,
    )
    async def authorize(
        request: Request, response: Response, scopes: list[str] = Query(None)
    ) -> OAuth2AuthorizeResponse:
        authorize_redirect_url = oauth_callback_redirect_uri(request)
        csrf_token = generate_csrf_token()
        state_data: dict[str, str] = {CSRF_TOKEN_KEY: csrf_token}
        state = generate_state_token(state_data, state_secret)
        authorization_url = await oauth_client.get_authorization_url(
            authorize_redirect_url,
            state,
            scopes,
        )
        response.set_cookie(
            csrf_token_cookie_name,
            csrf_token,
            max_age=3600,
            path=csrf_token_cookie_path,
            domain=csrf_token_cookie_domain,
            secure=csrf_token_cookie_secure,
            httponly=csrf_token_cookie_httponly,
            samesite=csrf_token_cookie_samesite,
        )
        return OAuth2AuthorizeResponse(authorization_url=authorization_url)

    @router.get(
        "/callback",
        name=callback_route_name,
        description="The response varies based on the authentication backend used.",
        responses={
            status.HTTP_400_BAD_REQUEST: {
                "model": ErrorModel,
                "content": {
                    "application/json": {
                        "examples": {
                            "INVALID_STATE_TOKEN": {
                                "summary": "Invalid state token.",
                                "value": None,
                            },
                            ErrorCode.LOGIN_BAD_CREDENTIALS: {
                                "summary": "User is inactive.",
                                "value": {"detail": ErrorCode.LOGIN_BAD_CREDENTIALS},
                            },
                            ErrorCode.ACCESS_TOKEN_DECODE_ERROR: {
                                "summary": "Access token is error.",
                                "value": {"detail": ErrorCode.ACCESS_TOKEN_DECODE_ERROR},
                            },
                            ErrorCode.ACCESS_TOKEN_ALREADY_EXPIRED: {
                                "summary": "Access token is already expired.",
                                "value": {"detail": ErrorCode.ACCESS_TOKEN_ALREADY_EXPIRED},
                            },
                        }
                    }
                },
            },
        },
    )
    async def callback(
        request: Request,
        access_token_state: tuple[OAuth2Token, str] = Depends(oauth2_authorize_callback),
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
        strategy: Strategy[models.UP, models.ID] = Depends(backend.get_strategy),
    ):
        token, state = access_token_state

        try:
            state_data = decode_jwt(state, state_secret, [STATE_TOKEN_AUDIENCE])
        except jwt.DecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.ACCESS_TOKEN_DECODE_ERROR,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.ACCESS_TOKEN_ALREADY_EXPIRED,
            )

        cookie_csrf_token = request.cookies.get(csrf_token_cookie_name)
        state_csrf_token = state_data.get(CSRF_TOKEN_KEY)
        if (
            not cookie_csrf_token
            or not state_csrf_token
            or not secrets.compare_digest(cookie_csrf_token, state_csrf_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.OAUTH_INVALID_STATE,
            )

        account_id, account_email = await oauth_client.get_id_email(token["access_token"])

        if account_email is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.OAUTH_NOT_AVAILABLE_EMAIL,
            )

        try:
            user = await user_manager.oauth_callback(
                oauth_client.name,
                token["access_token"],
                account_id,
                account_email,
                token.get("expires_at"),
                token.get("refresh_token"),
                request,
                associate_by_email=associate_by_email,
                is_verified_by_default=is_verified_by_default,
            )
        except UserAlreadyExists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.OAUTH_USER_ALREADY_EXISTS,
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorCode.LOGIN_BAD_CREDENTIALS,
            )

        response = await backend.login(strategy, user)
        await user_manager.on_after_login(user, request, response)
        return response

    return router
