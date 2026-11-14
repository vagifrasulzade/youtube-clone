"""Version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1 import auth, channels, health, me, media, playlists, studio, videos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(videos.router)
api_router.include_router(channels.router)
api_router.include_router(media.router)
api_router.include_router(me.router)
api_router.include_router(playlists.router)
api_router.include_router(studio.router)
