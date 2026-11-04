"""UI/API boundary for canonical ResearchOrchestrator."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from contracts.research import ResearchRequest, ResearchOutput
from research.orchestrator import ResearchOrchestrator


class QueryService:
    def __init__(self, orchestrator: Optional[ResearchOrchestrator] = None):
        self.orchestrator = orchestrator or ResearchOrchestrator()
        self.resolver = self.orchestrator.resolver

    def query(self, query: str, horizon: str = "20D", as_of: Optional[datetime] = None) -> ResearchOutput:
        # 1. request_id and as_of generation
        request_id = str(uuid.uuid4())
        as_of_dt = as_of or datetime.now(timezone.utc)

        # 2. Query parsing (Korean / English natural language extraction)
        parsed_query = query.strip()
        suffixes = [" 분석해줘", " 분석해", " 분석", "을 분석해줘", "를 분석해줘"]
        for suffix in suffixes:
            if parsed_query.endswith(suffix):
                parsed_query = parsed_query[:-len(suffix)].strip()

        # 3. Entity Resolution invocation
        identity = self.resolver.resolve(parsed_query, request_id)

        # 4. ResearchOrchestrator invocation
        request = ResearchRequest(
            query=parsed_query,
            request_id=request_id,
            as_of=as_of_dt,
            horizon=horizon
        )
        return self.orchestrator.research(request)
