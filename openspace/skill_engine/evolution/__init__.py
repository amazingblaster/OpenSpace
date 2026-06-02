"""Evolution engine orchestration."""

from .admission import AdmissionResult, EvolutionAdmission
from .audit import EvidenceRefAccessError, EvolutionActionRecord, EvolutionAuditService
from .authoring import AuthoringResult, SkillEvolverAuthoringBackend, StagedSkillEdit
from .backfill import (
    BackfillResult,
    EvidenceBackfill,
    backfill_recording,
    backfill_session,
    backfill_skill_store,
)
from .candidates import EvolutionCandidate, EvolutionCandidateStore
from .engine import EvolutionCommitter, EvolutionEngine, EvolutionRunResult
from .job_completion import (
    EvolutionJobCompletion,
    completion_after_recovery,
    completion_from_outcome,
    outcome_has_committing_action,
    outcome_result_ref,
)
from .recovery import EvolutionRecovery, EvolutionRecoveryResult
from .validator import EvolutionValidator, ValidationResult

__all__ = [
    "AdmissionResult",
    "AuthoringResult",
    "BackfillResult",
    "EvidenceBackfill",
    "backfill_recording",
    "backfill_session",
    "backfill_skill_store",
    "EvolutionActionRecord",
    "EvolutionAuditService",
    "EvidenceRefAccessError",
    "EvolutionCandidate",
    "EvolutionCandidateStore",
    "EvolutionCommitter",
    "EvolutionAdmission",
    "EvolutionEngine",
    "EvolutionJobCompletion",
    "EvolutionRecovery",
    "EvolutionRecoveryResult",
    "EvolutionRunResult",
    "EvolutionValidator",
    "SkillEvolverAuthoringBackend",
    "StagedSkillEdit",
    "ValidationResult",
    "completion_after_recovery",
    "completion_from_outcome",
    "outcome_has_committing_action",
    "outcome_result_ref",
]
