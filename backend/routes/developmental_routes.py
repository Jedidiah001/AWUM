"""NXT developmental system routes."""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, current_app

from models.developmental_roster import DevelopmentalProspect
from simulation.call_up_engine import calculate_call_up_priority, build_call_up_recommendation


developmental_bp = Blueprint("developmental", __name__)


def _db():
    return current_app.config["DATABASE"]


def _pool():
    return current_app.config.get("FREE_AGENT_POOL")


def _now():
    return datetime.utcnow().isoformat()


def _ensure_tables():
    cur = _db().conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS developmental_roster (
            prospect_id TEXT PRIMARY KEY,
            free_agent_id TEXT NOT NULL,
            wrestler_name TEXT NOT NULL,
            assigned_brand TEXT NOT NULL DEFAULT 'ROC NXT',
            stage TEXT NOT NULL DEFAULT 'trainee',
            readiness_score REAL NOT NULL DEFAULT 0,
            promo_score REAL NOT NULL DEFAULT 0,
            in_ring_score REAL NOT NULL DEFAULT 0,
            consistency_score REAL NOT NULL DEFAULT 0,
            momentum_score REAL NOT NULL DEFAULT 0,
            projected_ceiling TEXT NOT NULL DEFAULT 'midcard',
            call_up_priority REAL NOT NULL DEFAULT 0,
            assigned_main_brand TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS developmental_events (
            event_id TEXT PRIMARY KEY,
            prospect_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """
    )
    _db().conn.commit()


@developmental_bp.route("/api/developmental/dashboard")
def developmental_dashboard():
    _ensure_tables()
    cur = _db().conn.cursor()
    cur.execute("SELECT * FROM developmental_roster ORDER BY call_up_priority DESC, wrestler_name")
    rows = [dict(r) for r in cur.fetchall()]
    return jsonify({"success": True, "count": len(rows), "roster": rows})


@developmental_bp.route("/api/developmental/add-prospect", methods=["POST"])
def add_prospect():
    _ensure_tables()
    data = request.get_json(silent=True) or {}
    fa_id = data.get("free_agent_id")
    if not fa_id:
        return jsonify({"success": False, "error": "free_agent_id is required"}), 400

    pool = _pool()
    fa = pool.get_free_agent_by_id(fa_id) if pool else None
    if not fa:
        return jsonify({"success": False, "error": "Prospect free agent not found"}), 404

    now = _now()
    pid = f"nxt_{uuid.uuid4().hex[:10]}"
    profile = DevelopmentalProspect(
        prospect_id=pid,
        free_agent_id=fa_id,
        wrestler_name=getattr(fa, "wrestler_name", "Unknown Prospect"),
        readiness_score=float(random.uniform(35, 70)),
        promo_score=float(random.uniform(30, 75)),
        in_ring_score=float(random.uniform(35, 80)),
        consistency_score=float(random.uniform(30, 70)),
        momentum_score=float(random.uniform(25, 70)),
        projected_ceiling=random.choice(["midcard", "upper_midcard", "main_event"]),
        created_at=now,
        updated_at=now,
    )
    profile.call_up_priority = calculate_call_up_priority(profile.to_dict())

    cur = _db().conn.cursor()
    cur.execute(
        """
        INSERT INTO developmental_roster (
            prospect_id, free_agent_id, wrestler_name, assigned_brand, stage,
            readiness_score, promo_score, in_ring_score, consistency_score, momentum_score,
            projected_ceiling, call_up_priority, assigned_main_brand, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile.prospect_id, profile.free_agent_id, profile.wrestler_name, profile.assigned_brand,
            profile.stage, profile.readiness_score, profile.promo_score, profile.in_ring_score,
            profile.consistency_score, profile.momentum_score, profile.projected_ceiling,
            profile.call_up_priority, profile.assigned_main_brand, profile.created_at, profile.updated_at,
        ),
    )
    _db().conn.commit()
    return jsonify({"success": True, "prospect": profile.to_dict()})


@developmental_bp.route("/api/developmental/call-up", methods=["POST"])
def call_up():
    _ensure_tables()
    data = request.get_json(silent=True) or {}
    prospect_id = data.get("prospect_id")
    target_brand = data.get("target_brand", "ROC Alpha")
    if not prospect_id:
        return jsonify({"success": False, "error": "prospect_id is required"}), 400

    cur = _db().conn.cursor()
    cur.execute("SELECT * FROM developmental_roster WHERE prospect_id=?", (prospect_id,))
    row = cur.fetchone()
    if not row:
        return jsonify({"success": False, "error": "Prospect not found"}), 404

    profile = dict(row)
    priority = calculate_call_up_priority(profile)
    recommendation = build_call_up_recommendation(priority)
    if priority < 60:
        return jsonify({"success": False, "error": "Prospect not call-up ready", "priority": priority, "recommendation": recommendation}), 400

    cur.execute(
        "UPDATE developmental_roster SET stage='called_up', assigned_main_brand=?, call_up_priority=?, updated_at=? WHERE prospect_id=?",
        (target_brand, priority, _now(), prospect_id),
    )
    _db().conn.commit()
    return jsonify({"success": True, "prospect_id": prospect_id, "target_brand": target_brand, "priority": priority, "recommendation": recommendation})
