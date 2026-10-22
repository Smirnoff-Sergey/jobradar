from fastapi import APIRouter

from app.api.v1 import auth, health, llm, resumes, search_profile, sources, vacancies

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(resumes.router)
api_router.include_router(search_profile.router)
api_router.include_router(vacancies.router)
api_router.include_router(sources.router)
api_router.include_router(llm.router)
