"""Application use cases coordinate domain logic via ports."""

from .add_result import (
    AddResultRequest,
    AddResultResponse,
    AddResultUseCase,
    ResultsRecorder,
)
from .get_progress import (
    GetProgressUseCase,
    StatsProvider,
    WeeklyProgressView,
)
from .get_prs_and_sob import (
    ComparisonView,
    GetPRsAndSOBUseCase,
    PRComparisonProvider,
)
from .manage_roles import (
    ManageRolesUseCase,
    RoleAssignment,
    RoleStore,
)
from .manage_templates import (
    ManageTemplatesUseCase,
    TemplateInput,
    TemplateRepository,
)
from .notify import (
    BroadcastRequest,
    NotifyUseCase,
    NotificationGateway,
)
from .search_results import (
    SearchFiltersInput,
    SearchPageView,
    SearchResultsUseCase,
    SearchResultsProvider,
)

__all__ = [
    "AddResultRequest",
    "AddResultResponse",
    "AddResultUseCase",
    "BroadcastRequest",
    "ComparisonView",
    "GetPRsAndSOBUseCase",
    "GetProgressUseCase",
    "ManageRolesUseCase",
    "ManageTemplatesUseCase",
    "NotificationGateway",
    "NotifyUseCase",
    "PRComparisonProvider",
    "ResultsRecorder",
    "RoleAssignment",
    "RoleStore",
    "SearchFiltersInput",
    "SearchPageView",
    "SearchResultsProvider",
    "SearchResultsUseCase",
    "StatsProvider",
    "TemplateInput",
    "TemplateRepository",
    "WeeklyProgressView",
]
