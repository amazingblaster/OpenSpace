from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[3]

from flask import Flask, abort, jsonify, request, send_from_directory, url_for

from openspace.recording.action_recorder import analyze_agent_actions, load_agent_actions
from openspace.recording.utils import load_recording_session
from openspace.skill_engine import SkillStore
from openspace.skill_engine.evidence import (
    EvidenceStore,
    resolve_evidence_db_path as resolve_evidence_store_db_path,
    resolve_skill_store_db_path,
)
from openspace.skill_engine.evolution import (
    EvidenceRefAccessError,
    EvolutionAuditService,
)
from openspace.skill_engine.triggers import TriggerStore
from openspace.skill_engine.types import SkillRecord

API_PREFIX = "/api/v1"
PACKAGE_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "apps" / "dashboard" / "dist"
PACKAGED_DASHBOARD_STATIC_DIR = PACKAGE_ROOT / "packaged" / "dashboard"
WORKFLOW_ROOTS = [
    PROJECT_ROOT / "logs" / "recordings",
    PROJECT_ROOT / "logs" / "trajectories",
    PROJECT_ROOT / "benchmarks" / "gdpval" / "results",
]

PIPELINE_STAGES = [
    {
        "id": "initialize",
        "title": "Initialize",
        "description": "Load LLM, grounding backends, recording, registry, analyzer, and evolver.",
    },
    {
        "id": "select-skills",
        "title": "Skill Selection",
        "description": "Select candidate skills and write selection metadata before execution.",
    },
    {
        "id": "phase-1-skill",
        "title": "Skill Phase",
        "description": "Run the task with injected skill context whenever matching skills exist.",
    },
    {
        "id": "phase-2-fallback",
        "title": "Tool Fallback",
        "description": "Fallback to tool-only execution when the skill-guided phase fails or no skills match.",
    },
    {
        "id": "analysis",
        "title": "Execution Analysis",
        "description": "Persist metadata, trajectory, and post-run execution judgments.",
    },
    {
        "id": "evolution",
        "title": "Skill Evolution",
        "description": "Trigger fix / derived / captured evolution and periodic quality checks.",
    },
]


def create_app(
    *,
    store: SkillStore | None = None,
    db_path: str | Path | None = None,
    evidence_store: EvidenceStore | None = None,
    evidence_db_path: str | Path | None = None,
    evolution_storage_root: str | Path | None = None,
    trigger_store: TriggerStore | None = None,
    trigger_engine: Any | None = None,
    evolution_engine: Any | None = None,
) -> Flask:
    app = Flask(__name__, static_folder=None)
    resolved_skill_db_path = _resolve_skill_store_db_path(
        db_path=db_path,
        evolution_storage_root=evolution_storage_root,
    )
    skill_store = store or SkillStore(resolved_skill_db_path)
    resolved_evidence_db_path = _resolve_evidence_db_path(
        evidence_db_path=evidence_db_path,
        db_path=db_path,
        evolution_storage_root=evolution_storage_root,
        skill_store=skill_store,
    )
    audit_evidence_store = evidence_store or EvidenceStore(
        resolved_evidence_db_path,
        allowed_read_roots=_dashboard_evidence_allowed_read_roots(
            evidence_db_path=resolved_evidence_db_path,
            db_path=db_path,
            evolution_storage_root=evolution_storage_root,
        ),
    )
    audit_trigger_store = trigger_store or getattr(trigger_engine, "store", None)
    if audit_trigger_store is None:
        audit_trigger_store = TriggerStore(evidence_store=audit_evidence_store)
    audit_service = EvolutionAuditService(
        audit_evidence_store,
        skill_store,
        trigger_store=audit_trigger_store,
        trigger_engine=trigger_engine,
        evolution_engine=evolution_engine,
    )

    def get_store() -> SkillStore:
        return skill_store

    def get_audit() -> EvolutionAuditService:
        return audit_service

    @app.route(f"{API_PREFIX}/health", methods=["GET"])
    def health() -> Any:
        workflows = _discover_workflow_dirs()
        store = get_store()
        return jsonify(
            {
                "status": "ok",
                "project_root": str(PROJECT_ROOT),
                "db_path": str(store.db_path),
                "evidence_db_path": str(audit_evidence_store.db_path),
                "db_exists": store.db_path.exists(),
                "evidence_db_exists": audit_evidence_store.db_path.exists(),
                "frontend_dist_exists": resolve_dashboard_static_dir() is not None,
                "workflow_roots": [str(path) for path in WORKFLOW_ROOTS],
                "workflow_count": len(workflows),
            }
        )

    @app.route(f"{API_PREFIX}/overview", methods=["GET"])
    def overview() -> Any:
        store = get_store()
        skills = list(store.load_all(active_only=False).values())
        workflows = [_build_workflow_summary(path) for path in _discover_workflow_dirs()]
        top_skills = _sort_skills(skills, sort_key="score")[:5]
        recent_skills = _sort_skills(skills, sort_key="updated")[:5]
        average_score = round(
            sum(_skill_score(record) for record in skills) / len(skills), 1
        ) if skills else 0.0
        average_workflow_success = round(
            (sum((item.get("success_rate") or 0.0) for item in workflows) / len(workflows)) * 100,
            1,
        ) if workflows else 0.0

        return jsonify(
            {
                "health": {
                    "status": "ok",
                    "db_path": str(store.db_path),
                    "evidence_db_path": str(audit_evidence_store.db_path),
                    "workflow_count": len(workflows),
                    "frontend_dist_exists": resolve_dashboard_static_dir() is not None,
                },
                "pipeline": PIPELINE_STAGES,
                "skills": {
                    "summary": _build_skill_stats(store, skills),
                    "average_score": average_score,
                    "top": [_serialize_skill(item) for item in top_skills],
                    "recent": [_serialize_skill(item) for item in recent_skills],
                },
                "workflows": {
                    "total": len(workflows),
                    "average_success_rate": average_workflow_success,
                    "recent": workflows[:5],
                },
            }
        )

    @app.route(f"{API_PREFIX}/skills", methods=["GET"])
    def list_skills() -> Any:
        store = get_store()
        active_only = _bool_arg("active_only", True)
        limit = _int_arg("limit", 100)
        sort_key = (_str_arg("sort", "score") or "score").lower()
        skills = list(store.load_all(active_only=active_only).values())
        query = (_str_arg("query", "") or "").strip().lower()
        if query:
            skills = [
                record
                for record in skills
                if query in record.name.lower()
                or query in record.skill_id.lower()
                or query in record.description.lower()
                or any(query in tag.lower() for tag in record.tags)
            ]
        items = [_serialize_skill(item) for item in _sort_skills(skills, sort_key=sort_key)[:limit]]
        return jsonify({"items": items, "count": len(items), "active_only": active_only})

    @app.route(f"{API_PREFIX}/skills/stats", methods=["GET"])
    def skill_stats() -> Any:
        store = get_store()
        skills = list(store.load_all(active_only=False).values())
        return jsonify(_build_skill_stats(store, skills))

    @app.route(f"{API_PREFIX}/skills/<skill_id>", methods=["GET"])
    def skill_detail(skill_id: str) -> Any:
        store = get_store()
        record = store.load_record(skill_id)
        if not record:
            abort(404, description=f"Unknown skill_id: {skill_id}")

        detail = _serialize_skill(record, include_recent_analyses=True)
        detail["recent_analyses"] = [analysis.to_dict() for analysis in store.load_analyses(skill_id=skill_id, limit=10)]
        detail["source"] = _load_skill_source(record)
        return jsonify(detail)

    @app.route(f"{API_PREFIX}/skills/<skill_id>/lineage", methods=["GET"])
    def skill_lineage(skill_id: str) -> Any:
        store = get_store()
        if not store.load_record(skill_id):
            abort(404, description=f"Unknown skill_id: {skill_id}")
        return jsonify(_build_lineage_payload(skill_id, store))

    @app.route(f"{API_PREFIX}/skills/<skill_id>/source", methods=["GET"])
    def skill_source(skill_id: str) -> Any:
        store = get_store()
        record = store.load_record(skill_id)
        if not record:
            abort(404, description=f"Unknown skill_id: {skill_id}")
        return jsonify(_load_skill_source(record))

    @app.route(f"{API_PREFIX}/evolution/jobs", methods=["GET"])
    def evolution_jobs() -> Any:
        status = _str_arg("status", "")
        limit = _int_arg("limit", 100)
        items = get_audit().list_jobs(status=status or None, limit=limit)
        return jsonify({"items": items, "count": len(items)})

    @app.route(f"{API_PREFIX}/evolution/jobs/<job_id>", methods=["GET"])
    def evolution_job(job_id: str) -> Any:
        payload = get_audit().get_job(job_id)
        if payload is None:
            abort(404, description=f"Unknown evolution job: {job_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evolution/packets/<packet_id>", methods=["GET"])
    def evolution_packet(packet_id: str) -> Any:
        payload = get_audit().get_packet(packet_id)
        if payload is None:
            abort(404, description=f"Unknown evidence packet: {packet_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evolution/decisions/<decision_id>", methods=["GET"])
    def evolution_decision(decision_id: str) -> Any:
        payload = get_audit().get_decision(decision_id)
        if payload is None:
            abort(404, description=f"Unknown evolution decision: {decision_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evolution/candidates", methods=["GET"])
    def evolution_candidates() -> Any:
        status = _str_arg("status", "pending")
        limit = _int_arg("limit", 100)
        items = get_audit().list_candidates(status=status, limit=limit)
        return jsonify({"items": items, "count": len(items), "status": status})

    @app.route(f"{API_PREFIX}/evolution/review-items", methods=["GET"])
    def evolution_review_items() -> Any:
        limit = _int_arg("limit", 100)
        items = get_audit().list_review_items(limit=limit)
        return jsonify({"items": items, "count": len(items)})

    @app.route(f"{API_PREFIX}/quality-signals", methods=["GET"])
    def quality_signals() -> Any:
        limit = _int_arg("limit", 100)
        subject_type = _str_arg("subject_type", "") or None
        subject_id = _str_arg("subject_id", "") or None
        actionability = _str_arg("actionability", "") or None
        not_triggerable = _bool_arg("not_triggerable", False)
        items = get_audit().list_quality_signals(
            subject_type=subject_type,
            subject_id=subject_id,
            actionability=actionability,
            not_triggerable=not_triggerable,
            limit=limit,
        )
        return jsonify({"items": items, "count": len(items)})

    @app.route(f"{API_PREFIX}/quality-signals/jobs", methods=["GET"])
    def quality_signal_jobs() -> Any:
        limit = _int_arg("limit", 100)
        items = get_audit().list_quality_signal_jobs(limit=limit)
        return jsonify({"items": items, "count": len(items)})

    @app.route(f"{API_PREFIX}/evolution/candidates/<candidate_id>", methods=["GET"])
    def evolution_candidate(candidate_id: str) -> Any:
        payload = get_audit().get_candidate(candidate_id)
        if payload is None:
            abort(404, description=f"Unknown evolution candidate: {candidate_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evolution/candidates/<candidate_id>/reject", methods=["POST"])
    def reject_evolution_candidate(candidate_id: str) -> Any:
        body = request.get_json(silent=True) or {}
        reason = str(body.get("reason") or "").strip()
        if not reason:
            reason = "manual reject"
        try:
            payload = get_audit().reject_candidate(candidate_id, reason)
        except KeyError:
            abort(404, description=f"Unknown evolution candidate: {candidate_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evolution/candidates/<candidate_id>/request-recheck", methods=["POST"])
    def request_recheck_evolution_candidate(candidate_id: str) -> Any:
        run_now = _bool_arg("run_now", True)
        try:
            payload = get_audit().request_candidate_recheck(
                candidate_id,
                run_now=run_now,
            )
        except KeyError:
            abort(404, description=f"Unknown evolution candidate: {candidate_id}")
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(payload), 202

    @app.route(f"{API_PREFIX}/evolution/actions/<action_id>", methods=["GET"])
    def evolution_action(action_id: str) -> Any:
        payload = get_audit().get_action(action_id)
        if payload is None:
            abort(404, description=f"Unknown evolution action: {action_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evidence/refs/<path:ref_id>/preview", methods=["GET"])
    def evidence_ref_preview(ref_id: str) -> Any:
        max_chars = _int_arg("max_chars", 2000)
        try:
            payload = get_audit().read_ref(ref_id, max_chars=max_chars)
        except KeyError:
            abort(404, description=f"Unknown evidence ref: {ref_id}")
        except EvidenceRefAccessError as exc:
            return jsonify({"error": exc.reason, "ref_id": ref_id}), exc.status_code
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/evidence/refs/<path:ref_id>", methods=["GET"])
    def evidence_ref(ref_id: str) -> Any:
        include_preview = _bool_arg("include_preview", True)
        payload = get_audit().get_ref(ref_id, include_preview=include_preview)
        if payload is None:
            abort(404, description=f"Unknown evidence ref: {ref_id}")
        return jsonify(payload)

    @app.route(f"{API_PREFIX}/workflows", methods=["GET"])
    def list_workflows() -> Any:
        items = [_build_workflow_summary(path) for path in _discover_workflow_dirs()]
        return jsonify({"items": items, "count": len(items)})

    @app.route(f"{API_PREFIX}/workflows/<workflow_id>", methods=["GET"])
    def workflow_detail(workflow_id: str) -> Any:
        workflow_dir = _get_workflow_dir(workflow_id)
        if not workflow_dir:
            abort(404, description=f"Unknown workflow: {workflow_id}")

        session = load_recording_session(str(workflow_dir))
        actions = load_agent_actions(str(workflow_dir))
        metadata = session.get("metadata") or {}
        trajectory = session.get("trajectory") or []
        plans = session.get("plans") or []
        decisions = session.get("decisions") or []
        action_stats = analyze_agent_actions(actions)

        enriched_trajectory = []
        for step in trajectory:
            step_copy = dict(step)
            screenshot_rel = step_copy.get("screenshot")
            if screenshot_rel:
                step_copy["screenshot_url"] = url_for(
                    "workflow_artifact",
                    workflow_id=workflow_id,
                    artifact_path=screenshot_rel,
                )
            enriched_trajectory.append(step_copy)

        timeline = _build_timeline(actions, enriched_trajectory)
        artifacts = _build_workflow_artifacts(workflow_dir, workflow_id, metadata)

        return jsonify(
            {
                **_build_workflow_summary(workflow_dir),
                "metadata": metadata,
                "statistics": session.get("statistics") or {},
                "trajectory": enriched_trajectory,
                "plans": plans,
                "decisions": decisions,
                "agent_actions": actions,
                "agent_statistics": action_stats,
                "timeline": timeline,
                "artifacts": artifacts,
            }
        )

    @app.route(f"{API_PREFIX}/workflows/<workflow_id>/artifacts/<path:artifact_path>", methods=["GET"])
    def workflow_artifact(workflow_id: str, artifact_path: str) -> Any:
        workflow_dir = _get_workflow_dir(workflow_id)
        if not workflow_dir:
            abort(404, description=f"Unknown workflow: {workflow_id}")

        target = (workflow_dir / artifact_path).resolve()
        root = workflow_dir.resolve()
        if root not in target.parents and target != root:
            abort(404)
        if not target.exists() or not target.is_file():
            abort(404)
        return send_from_directory(str(target.parent), target.name)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str) -> Any:
        if path.startswith("api/"):
            abort(404)

        static_dir = resolve_dashboard_static_dir()
        if static_dir is not None:
            requested = static_dir / path if path else static_dir / "index.html"
            if path and requested.exists() and requested.is_file():
                return send_from_directory(str(static_dir), path)
            return send_from_directory(str(static_dir), "index.html")

        return jsonify(
            {
                "message": "OpenSpace dashboard API is running.",
                "frontend": _dashboard_static_fallback_message(),
            }
        )

    return app


def dashboard_static_dir_candidates() -> List[Path]:
    if running_from_source_checkout():
        return [FRONTEND_DIST_DIR]
    return [PACKAGED_DASHBOARD_STATIC_DIR]


def running_from_source_checkout() -> bool:
    return (PROJECT_ROOT / "pyproject.toml").is_file() and (
        PROJECT_ROOT / "apps" / "dashboard"
    ).is_dir()


def resolve_dashboard_static_dir() -> Optional[Path]:
    for candidate in dashboard_static_dir_candidates():
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


def _dashboard_static_fallback_message() -> str:
    searched = ", ".join(str(path) for path in dashboard_static_dir_candidates())
    if running_from_source_checkout():
        return (
            "No dashboard frontend dist found. Build the source dashboard with "
            "`npm --prefix apps/dashboard run build`. "
            f"Searched: {searched}"
        )
    return (
        "No packaged dashboard frontend found. Reinstall OpenSpace from a "
        "package built with `npm --prefix apps/dashboard run build:packaged`. "
        f"Searched: {searched}"
    )


def _bool_arg(name: str, default: bool) -> bool:
    from flask import request

    raw = request.args.get(name)
    if raw is None:
        return default
    return raw.lower() not in {"0", "false", "no", "off"}


def _int_arg(name: str, default: int) -> int:
    from flask import request

    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _str_arg(name: str, default: str) -> str:
    from flask import request

    return request.args.get(name, default)


def _resolve_evidence_db_path(
    *,
    evidence_db_path: str | Path | None,
    db_path: str | Path | None,
    evolution_storage_root: str | Path | None = None,
    skill_store: SkillStore,
) -> Path:
    if evidence_db_path is not None:
        return Path(evidence_db_path).expanduser().resolve()
    explicit = os.environ.get("OPENSPACE_EVOLUTION_EVIDENCE_DB_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    storage_root = evolution_storage_root or os.environ.get("OPENSPACE_EVOLUTION_STORAGE_ROOT")
    return resolve_evidence_store_db_path(
        storage_root=storage_root,
        skill_store=skill_store,
    )


def _resolve_skill_store_db_path(
    *,
    db_path: str | Path | None,
    evolution_storage_root: str | Path | None = None,
) -> Path | None:
    if db_path is not None:
        return Path(db_path).expanduser().resolve()
    explicit = os.environ.get("OPENSPACE_SKILL_STORE_DB_PATH")
    if explicit:
        return Path(explicit).expanduser().resolve()
    storage_root = evolution_storage_root or os.environ.get("OPENSPACE_EVOLUTION_STORAGE_ROOT")
    return resolve_skill_store_db_path(
        storage_root=storage_root,
        workspace_dir=PROJECT_ROOT,
    )


def _dashboard_evidence_allowed_read_roots(
    *,
    evidence_db_path: Path,
    db_path: str | Path | None,
    evolution_storage_root: str | Path | None,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    _append_root(roots, evidence_db_path.parent)
    if db_path is not None:
        _append_root(roots, Path(db_path).expanduser().resolve().parent)
    storage_root = evolution_storage_root or os.environ.get("OPENSPACE_EVOLUTION_STORAGE_ROOT")
    if storage_root:
        _append_root(roots, storage_root)
        _append_root(roots, Path(storage_root).expanduser().resolve() / ".openspace" / "evolution")
    env_roots = os.environ.get("OPENSPACE_EVOLUTION_ALLOWED_READ_ROOTS", "")
    for item in env_roots.split(os.pathsep):
        _append_root(roots, item)
    return tuple(roots)


def _append_root(roots: list[Path], root: str | Path | None) -> None:
    if not root:
        return
    try:
        path = Path(root).expanduser()
        if path.is_file():
            path = path.parent
        resolved = path.resolve()
    except (OSError, TypeError, ValueError):
        return
    if resolved not in roots:
        roots.append(resolved)


def _skill_score(record: SkillRecord) -> float:
    return round(record.effective_rate * 100, 1)


def _skill_has_activity(record: SkillRecord) -> bool:
    return any(
        value > 0
        for value in (
            record.total_uses,
            record.total_applied,
            record.total_completions,
            record.total_fallbacks,
        )
    ) or bool(record.recent_analyses)


def _serialize_skill(record: SkillRecord, *, include_recent_analyses: bool = False) -> Dict[str, Any]:
    payload = record.to_dict()
    if not include_recent_analyses:
        payload.pop("recent_analyses", None)

    path = payload.get("path", "")
    lineage = payload.get("lineage") or {}
    payload.update(
        {
            "skill_dir": str(Path(path).parent) if path else "",
            "origin": lineage.get("origin", ""),
            "generation": lineage.get("generation", 0),
            "parent_skill_ids": lineage.get("parent_skill_ids", []),
            "applied_rate": round(record.applied_rate, 4),
            "completion_rate": round(record.completion_rate, 4),
            "effective_rate": round(record.effective_rate, 4),
            "fallback_rate": round(record.fallback_rate, 4),
            "score": _skill_score(record),
            "latest_evolution_action_id": lineage.get("evolution_action_id"),
            "evolution_provenance_refs": lineage.get("provenance_refs", []),
        }
    )
    return payload


def _naive_dt(dt: datetime) -> datetime:
    """Strip tzinfo so naive/aware datetimes can be compared safely."""
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _sort_skills(records: Iterable[SkillRecord], *, sort_key: str) -> List[SkillRecord]:
    if sort_key == "updated":
        return sorted(records, key=lambda item: _naive_dt(item.last_updated), reverse=True)
    if sort_key == "name":
        return sorted(records, key=lambda item: item.name.lower())
    return sorted(
        records,
        key=lambda item: (_skill_score(item), item.total_uses, _naive_dt(item.last_updated).timestamp()),
        reverse=True,
    )


def _build_skill_stats(store: SkillStore, skills: List[SkillRecord]) -> Dict[str, Any]:
    stats = store.get_stats(active_only=False)
    avg_score = round(sum(_skill_score(item) for item in skills) / len(skills), 1) if skills else 0.0
    skills_with_recent_analysis = sum(1 for item in skills if item.recent_analyses)
    return {
        **stats,
        "average_score": avg_score,
        "skills_with_activity": sum(1 for item in skills if _skill_has_activity(item)),
        "skills_with_recent_analysis": skills_with_recent_analysis,
        "top_by_effective_rate": [_serialize_skill(item) for item in _sort_skills(skills, sort_key="score")[:5]],
    }


def _load_skill_source(record: SkillRecord) -> Dict[str, Any]:
    skill_path = Path(record.path)
    if not skill_path.exists() or not skill_path.is_file():
        return {"exists": False, "path": record.path, "content": None}
    try:
        return {
            "exists": True,
            "path": str(skill_path),
            "content": skill_path.read_text(encoding="utf-8"),
        }
    except OSError:
        return {"exists": False, "path": str(skill_path), "content": None}


def _build_lineage_payload(skill_id: str, store: SkillStore) -> Dict[str, Any]:
    records = store.load_all(active_only=False)
    if skill_id not in records:
        return {"skill_id": skill_id, "nodes": [], "edges": [], "total_nodes": 0}

    children_by_parent: Dict[str, set[str]] = {}
    for item in records.values():
        for parent_id in item.lineage.parent_skill_ids:
            children_by_parent.setdefault(parent_id, set()).add(item.skill_id)

    related_ids = {skill_id}
    frontier = [skill_id]
    while frontier:
        current = frontier.pop()
        record = records.get(current)
        if not record:
            continue
        for parent_id in record.lineage.parent_skill_ids:
            if parent_id not in related_ids:
                related_ids.add(parent_id)
                frontier.append(parent_id)
        for child_id in children_by_parent.get(current, set()):
            if child_id not in related_ids:
                related_ids.add(child_id)
                frontier.append(child_id)

    nodes = []
    edges = []
    for related_id in sorted(related_ids):
        record = records.get(related_id)
        if not record:
            continue
        nodes.append(
            {
                "skill_id": record.skill_id,
                "name": record.name,
                "description": record.description,
                "origin": record.lineage.origin.value,
                "generation": record.lineage.generation,
                "created_at": record.lineage.created_at.isoformat(),
                "visibility": record.visibility.value,
                "is_active": record.is_active,
                "tags": list(record.tags),
                "score": _skill_score(record),
                "effective_rate": round(record.effective_rate, 4),
                "total_selections": record.total_selections,
            }
        )
        for parent_id in record.lineage.parent_skill_ids:
            if parent_id in related_ids:
                edges.append({"source": parent_id, "target": record.skill_id})

    return {
        "skill_id": skill_id,
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
    }


def _workflow_id(workflow_dir: Path) -> str:
    """Stable short ID for a workflow directory, unique across roots.

    Uses a hash suffix derived from the resolved path to avoid collisions
    when directory names contain the separator character.
    """
    import hashlib
    resolved = str(workflow_dir.resolve())
    path_hash = hashlib.sha256(resolved.encode()).hexdigest()[:8]
    return f"{workflow_dir.name}_{path_hash}"


def _discover_workflow_dirs() -> List[Path]:
    discovered: Dict[str, Path] = {}
    for root in WORKFLOW_ROOTS:
        if not root.exists():
            continue
        _scan_workflow_tree(root, discovered)
    return sorted(discovered.values(), key=lambda item: item.stat().st_mtime, reverse=True)


def _scan_workflow_tree(directory: Path, discovered: Dict[str, Path], *, _depth: int = 0, _max_depth: int = 6) -> None:
    if _depth > _max_depth:
        return
    try:
        children = list(directory.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_dir():
            continue
        if (child / "metadata.json").exists() or (child / "traj.jsonl").exists():
            discovered.setdefault(str(child.resolve()), child)
        else:
            _scan_workflow_tree(child, discovered, _depth=_depth + 1, _max_depth=_max_depth)


def _get_workflow_dir(workflow_id: str) -> Optional[Path]:
    for path in _discover_workflow_dirs():
        if _workflow_id(path) == workflow_id:
            return path
    return None


def _build_workflow_summary(workflow_dir: Path) -> Dict[str, Any]:
    session = load_recording_session(str(workflow_dir))
    metadata = session.get("metadata") or {}
    statistics = session.get("statistics") or {}
    actions = load_agent_actions(str(workflow_dir))
    screenshots_dir = workflow_dir / "screenshots"
    screenshot_count = len(list(screenshots_dir.glob("*.png"))) if screenshots_dir.exists() else 0

    video_candidates = [workflow_dir / "screen_recording.mp4", workflow_dir / "recording.mp4"]
    video_url = None
    for candidate in video_candidates:
        if candidate.exists():
            rel = candidate.relative_to(workflow_dir).as_posix()
            video_url = url_for("workflow_artifact", workflow_id=_workflow_id(workflow_dir), artifact_path=rel)
            break

    outcome = metadata.get("execution_outcome") or {}
    # Instruction fallback chain: top-level → retrieved_tools.instruction → skill_selection.task
    instruction = (
        metadata.get("instruction")
        or (metadata.get("retrieved_tools") or {}).get("instruction")
        or (metadata.get("skill_selection") or {}).get("task")
        or ""
    )

    # Resolve start/end times with trajectory fallback
    start_time = metadata.get("start_time")
    end_time = metadata.get("end_time")
    trajectory = session.get("trajectory") or []

    # If end_time is missing, infer from last trajectory step
    if not end_time and trajectory:
        last_ts = trajectory[-1].get("timestamp")
        if last_ts:
            end_time = last_ts

    # Compute execution_time: prefer outcome, fallback to timestamp diff
    execution_time = outcome.get("execution_time", 0)
    if not execution_time and start_time and end_time:
        try:
            t0 = datetime.fromisoformat(start_time)
            t1 = datetime.fromisoformat(end_time)
            execution_time = round((t1 - t0).total_seconds(), 2)
        except (ValueError, TypeError):
            pass

    # Resolve status: prefer outcome, fallback heuristic
    status = outcome.get("status", "")
    if not status:
        total_steps = int(statistics.get("total_steps") or 0)
        success_count = int(statistics.get("success_count") or 0)
        if total_steps > 0 and success_count >= total_steps:
            status = "success"
        elif total_steps > 0 and success_count > 0:
            status = "partial"
        elif total_steps > 0:
            status = "error"
        elif trajectory:
            status = "completed"
        else:
            status = "unknown"

    # Resolve iterations: prefer outcome, fallback to conversation count
    iterations = outcome.get("iterations", 0)
    if not iterations and trajectory:
        iterations = len(trajectory)

    return {
        "id": _workflow_id(workflow_dir),
        "path": str(workflow_dir),
        "task_id": metadata.get("task_id") or metadata.get("task_name") or workflow_dir.name,
        "task_name": metadata.get("task_name") or metadata.get("task_id") or workflow_dir.name,
        "instruction": instruction,
        "status": status,
        "iterations": iterations,
        "execution_time": execution_time,
        "start_time": start_time,
        "end_time": end_time,
        "total_steps": statistics.get("total_steps", 0),
        "success_count": statistics.get("success_count", 0),
        "success_rate": statistics.get("success_rate", 0.0),
        "backend_counts": statistics.get("backends", {}),
        "tool_counts": statistics.get("tools", {}),
        "agent_action_count": len(actions),
        "has_video": bool(video_url),
        "video_url": video_url,
        "screenshot_count": screenshot_count,
        "selected_skills": (metadata.get("skill_selection") or {}).get("selected", []),
    }


def _build_timeline(actions: List[Dict[str, Any]], trajectory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for action in actions:
        events.append(
            {
                "timestamp": action.get("timestamp", ""),
                "type": "agent_action",
                "step": action.get("step"),
                "label": action.get("action_type", "agent_action"),
                "agent_name": action.get("agent_name", ""),
                "agent_type": action.get("agent_type", ""),
                "details": action,
            }
        )
    for step in trajectory:
        events.append(
            {
                "timestamp": step.get("timestamp", ""),
                "type": "tool_execution",
                "step": step.get("step"),
                "label": step.get("tool", "tool_execution"),
                "backend": step.get("backend", ""),
                "status": (step.get("result") or {}).get("status", "unknown"),
                "details": step,
            }
        )
    events.sort(key=lambda item: (item.get("timestamp", ""), item.get("step") or 0))
    return events


def _build_workflow_artifacts(workflow_dir: Path, workflow_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    screenshots: List[Dict[str, Any]] = []
    screenshots_dir = workflow_dir / "screenshots"
    if screenshots_dir.exists():
        for image in sorted(screenshots_dir.glob("*.png")):
            rel = image.relative_to(workflow_dir).as_posix()
            screenshots.append(
                {
                    "name": image.name,
                    "path": rel,
                    "url": url_for("workflow_artifact", workflow_id=workflow_id, artifact_path=rel),
                }
            )

    init_screenshot = metadata.get("init_screenshot")
    init_screenshot_url = (
        url_for("workflow_artifact", workflow_id=workflow_id, artifact_path=init_screenshot)
        if isinstance(init_screenshot, str)
        else None
    )

    video_url = None
    for rel in ("screen_recording.mp4", "recording.mp4"):
        candidate = workflow_dir / rel
        if candidate.exists():
            video_url = url_for("workflow_artifact", workflow_id=workflow_id, artifact_path=rel)
            break

    return {
        "init_screenshot_url": init_screenshot_url,
        "screenshots": screenshots,
        "video_url": video_url,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenSpace dashboard API server")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard API host")
    parser.add_argument("--port", type=int, default=7788, help="Dashboard API port")
    parser.add_argument("--db-path", default=None, help="Dashboard skill store path")
    parser.add_argument(
        "--evidence-db-path",
        default=None,
        help="Dashboard evidence/audit store path; defaults to evidence.db next to --db-path",
    )
    parser.add_argument(
        "--evolution-storage-root",
        default=None,
        help="Workspace/evolution storage root containing .openspace/evidence.db",
    )
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    app = create_app(
        db_path=args.db_path,
        evidence_db_path=args.evidence_db_path,
        evolution_storage_root=args.evolution_storage_root,
    )

    from werkzeug.serving import run_simple
    run_simple(
        args.host,
        args.port,
        app,
        threaded=True,
        use_debugger=args.debug,
        use_reloader=args.debug,
    )


if __name__ == "__main__":
    main()
