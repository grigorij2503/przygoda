from fastapi import APIRouter

from app.schemas import CampaignEndingDraftJobResponse, GenerateIntroResponse
from app.services import session_service


router = APIRouter()
router.add_api_route(
    "/api/session",
    session_service.get_current_session,
    methods=["GET"],
)
router.add_api_route(
    "/api/generate-intro",
    session_service.generate_intro,
    methods=["POST"],
    response_model=GenerateIntroResponse,
)
router.add_api_route(
    "/api/session/reset-campaign",
    session_service.reset_campaign,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/setup-scenario",
    session_service.setup_scenario,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/start-prologue",
    session_service.start_prologue,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/generate-ending-draft",
    session_service.generate_campaign_ending_draft,
    methods=["POST"],
    response_model=CampaignEndingDraftJobResponse,
    status_code=202,
)
router.add_api_route(
    "/api/session/generate-ending-draft",
    session_service.get_campaign_ending_draft_job,
    methods=["GET"],
    response_model=CampaignEndingDraftJobResponse,
)
router.add_api_route(
    "/api/session/finish-campaign",
    session_service.finish_campaign,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/resolve-party-crisis",
    session_service.resolve_party_crisis,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/name-entity",
    session_service.name_entity,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/trigger-naming",
    session_service.trigger_naming,
    methods=["POST"],
)
