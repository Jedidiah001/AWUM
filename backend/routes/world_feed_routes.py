"""Real-time world feed routes (Phase A)."""

from __future__ import annotations

import json
import random
import uuid
from datetime import datetime
from flask import Blueprint, current_app, jsonify, request

world_feed_bp = Blueprint("world_feed", __name__)


def _db():
    return current_app.config["DATABASE"]


def _cursor():
    return _db().conn.cursor()


def _now():
    return datetime.now().isoformat()


def _year_week():
    gs = _db().get_game_state()
    return int(gs.get("current_year", 1)), int(gs.get("current_week", 1))


def _jloads(v, default):
    try:
        return json.loads(v) if isinstance(v, str) else (v if v is not None else default)
    except Exception:
        return default


def _jdumps(v):
    return json.dumps(v, ensure_ascii=False)


def _story_from_evolve_event(event: dict) -> dict:
    payload = _jloads(event.get("payload_json"), {})
    et = event.get("event_type", "generic")

    if et == "training_injury":
        name = payload.get("wrestler_name", "A prospect")
        weeks = payload.get("injury_weeks", 0)
        return {
            "headline": f"🚑 Evolve Injury Alert: {name} sidelined",
            "details": {"event_type": et, "weeks": weeks, "payload": payload},
            "impact": {"morale_delta": -2, "buzz_delta": 1, "development_velocity": -1},
            "significance": 4,
        }

    if et == "call_up":
        name = payload.get("wrestler_name", "Prospect")
        return {
            "headline": f"📈 Call-Up Buzz: {name} reaches main roster",
            "details": {"event_type": et, "payload": payload},
            "impact": {"ratings_delta": 1, "buzz_delta": 3, "morale_delta": 1},
            "significance": 3,
        }

    if et == "tryout_held":
        count = payload.get("count", 0)
        return {
            "headline": f"🎯 Tryout Wave: Evolve scouts {count} new prospects",
            "details": {"event_type": et, "payload": payload},
            "impact": {"scouting_momentum": 2, "buzz_delta": 1},
            "significance": 2,
        }

    if et == "international_excursion":
        name = payload.get("wrestler_name", "Prospect")
        destination = payload.get("destination", "abroad")
        return {
            "headline": f"✈️ Excursion Update: {name} sent to {destination}",
            "details": {"event_type": et, "payload": payload},
            "impact": {"in_ring_growth": 2, "buzz_delta": 1},
            "significance": 2,
        }

    if et == "developmental_show":
        matches = payload.get("match_count", 0)
        return {
            "headline": f"🎬 Evolve Showcase airs with {matches} developmental matches",
            "details": {"event_type": et, "payload": payload},
            "impact": {"development_velocity": 1, "buzz_delta": 1},
            "significance": 2,
        }

    generic = [
        "📰 Backstage chatter grows after a busy Evolve week",
        "📣 Fans are discussing Evolve’s latest performance updates",
        "🎙️ Industry pundits note momentum in your talent pipeline",
    ]
    return {
        "headline": random.choice(generic),
        "details": {"event_type": et, "payload": payload},
        "impact": {"buzz_delta": 1},
        "significance": 1,
    }


@world_feed_bp.route("/api/world/tick", methods=["POST"])
def world_tick():
    """Generate up to N world-feed stories from recent evolve events."""
    data = request.get_json(force=True, silent=True) or {}
    max_items = max(1, min(10, int(data.get("max_items", 3))))

    cur = _cursor()
    year, week = _year_week()

    cur.execute(
        """
        SELECT * FROM evolve_events
        ORDER BY created_at DESC
        LIMIT 25
        """
    )
    events = [dict(r) for r in cur.fetchall()]

    created = []
    for ev in events:
        if len(created) >= max_items:
            break

        source_event_id = ev.get("event_id")
        cur.execute("SELECT 1 FROM world_feed WHERE source_event_id=? LIMIT 1", (source_event_id,))
        if cur.fetchone():
            continue

        story = _story_from_evolve_event(ev)
        feed_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO world_feed (
                feed_id, year, week, source_type, source_event_id,
                headline, details_json, impact_json, significance, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id,
                year,
                week,
                "evolve_event",
                source_event_id,
                story["headline"],
                _jdumps(story["details"]),
                _jdumps(story["impact"]),
                int(story.get("significance", 1)),
                _now(),
            ),
        )

        if int(story.get("significance", 1)) >= 4:
            cur.execute(
                """
                INSERT INTO historical_moments (
                    moment_id, year, week, show_id, title, description,
                    significance_level, tags_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"hm_{uuid.uuid4().hex[:12]}",
                    year,
                    week,
                    "",
                    story["headline"],
                    "Auto-promoted from world feed due to high significance.",
                    int(story.get("significance", 1)),
                    _jdumps(["world_feed", "auto_promoted"]),
                    _now(),
                ),
            )

        created.append(feed_id)

    if not created:
        # Keep world alive even on quiet weeks
        ambience_headline = random.choice([
            "🌍 Quiet Week: Fans await your next major booking move",
            "📺 TV chatter steady as the roster prepares for upcoming angles",
            "🎟️ Attendance speculation rises ahead of your next card",
        ])
        feed_id = f"wf_{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO world_feed (
                feed_id, year, week, source_type, source_event_id,
                headline, details_json, impact_json, significance, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feed_id,
                year,
                week,
                "ambient",
                None,
                ambience_headline,
                _jdumps({"kind": "ambient"}),
                _jdumps({"buzz_delta": 0}),
                1,
                _now(),
            ),
        )
        created.append(feed_id)

    _db().conn.commit()
    return jsonify({"ok": True, "created": len(created), "feed_ids": created})


@world_feed_bp.route("/api/world/feed", methods=["GET"])
def get_world_feed():
    """Get live world-feed stories with optional cursor-like filtering."""
    since = request.args.get("since", "").strip()
    limit = max(1, min(100, int(request.args.get("limit", 30))))

    cur = _cursor()
    if since:
        cur.execute(
            """
            SELECT * FROM world_feed
            WHERE created_at > ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (since, limit),
        )
    else:
        cur.execute(
            """
            SELECT * FROM world_feed
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    rows = []
    for r in cur.fetchall():
        d = dict(r)
        d["details"] = _jloads(d.get("details_json"), {})
        d["impact"] = _jloads(d.get("impact_json"), {})
        rows.append(d)

    return jsonify({"ok": True, "items": rows})
