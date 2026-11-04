"""Provider-free canonical resolution; discovery is deliberately optional."""

import re
from typing import Optional

from contracts.security import IdentityStatus, SecurityIdentity
from .security_master import SecurityMaster


class EntityResolutionService:
    def __init__(self, master: Optional[SecurityMaster] = None):
        self.master = master or SecurityMaster()

    @staticmethod
    def normalize(query: str) -> str:
        return re.sub(r"\s+", " ", (query or "").strip()).lower()

    def resolve(self, query: str, request_id: str = "") -> SecurityIdentity:
        candidates = self.master.candidates(self.normalize(query))
        if not candidates:
            candidates = self.master.fuzzy_candidates(self.normalize(query))
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return SecurityIdentity(None, company_name=query, identity_status=IdentityStatus.AMBIGUOUS,
                                    resolution_confidence=0.0)
        return SecurityIdentity.unresolved(query)
