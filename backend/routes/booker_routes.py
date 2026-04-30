from __future__ import annotations

import json
import uuid
from datetime import datetime
from flask import Blueprint, current_app, jsonify, request

booker_bp = Blueprint('booker', __name__)

PERSONALITIES = {"veteran", "marketer", "historian", "anarchist"}
PRIORITIES = {"urgent", "opportunity", "spark"}
STATUSES = {"open", "accepted", "rejected", "modified", "pinned", "dismissed"}


def get_database():
    return current_app.config['DATABASE']


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec='seconds') + 'Z'


def _ensure_tables(db):
    c = db.conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS creative_assistant_profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            personality TEXT NOT NULL DEFAULT 'veteran',
            risk_tolerance REAL NOT NULL DEFAULT 0.5,
            storytelling_tempo REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS booker_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            headline TEXT NOT NULL,
            rationale TEXT NOT NULL,
            options_json TEXT NOT NULL,
            projections_json TEXT NOT NULL,
            context_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            response_reason TEXT,
            counter_pitch TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS creative_notebook_entries (
            entry_id TEXT PRIMARY KEY,
            suggestion_id TEXT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            tag TEXT,
            pinned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (suggestion_id) REFERENCES booker_suggestions(suggestion_id)
        )
    ''')
    db.conn.commit()


def _row_to_suggestion(row):
    d = dict(row)
    d['options'] = json.loads(d.pop('options_json'))
    d['projections'] = json.loads(d.pop('projections_json'))
    d['context'] = json.loads(d.pop('context_json'))
    return d


@booker_bp.route('/api/booker/profile', methods=['GET', 'PUT'])
def booker_profile():
    db = get_database()
    _ensure_tables(db)
    c = db.conn.cursor()
    if request.method == 'PUT':
        payload = request.get_json(silent=True) or {}
        personality = str(payload.get('personality', 'veteran')).lower()
        if personality not in PERSONALITIES:
            return jsonify({'error': 'Invalid personality'}), 400
        risk = max(0.0, min(1.0, float(payload.get('risk_tolerance', 0.5))))
        tempo = max(0.0, min(1.0, float(payload.get('storytelling_tempo', 0.5))))
        c.execute('''
            INSERT INTO creative_assistant_profile (id, personality, risk_tolerance, storytelling_tempo, updated_at)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET personality=excluded.personality,
                risk_tolerance=excluded.risk_tolerance, storytelling_tempo=excluded.storytelling_tempo,
                updated_at=excluded.updated_at
        ''', (personality, risk, tempo, _now_iso()))
        db.conn.commit()

    row = c.execute('SELECT * FROM creative_assistant_profile WHERE id = 1').fetchone()
    if not row:
        c.execute('INSERT INTO creative_assistant_profile (id, personality, risk_tolerance, storytelling_tempo, updated_at) VALUES (1, ?, ?, ?, ?)',
                  ('veteran', 0.5, 0.5, _now_iso()))
        db.conn.commit()
        row = c.execute('SELECT * FROM creative_assistant_profile WHERE id = 1').fetchone()
    return jsonify(dict(row))


@booker_bp.route('/api/booker/suggestions', methods=['GET', 'POST'])
def suggestions():
    db = get_database()
    _ensure_tables(db)
    c = db.conn.cursor()

    if request.method == 'POST':
        p = request.get_json(silent=True) or {}
        priority = str(p.get('priority', 'opportunity')).lower()
        status = str(p.get('status', 'open')).lower()
        if priority not in PRIORITIES or status not in STATUSES:
            return jsonify({'error': 'Invalid priority or status'}), 400

        sid = f"sg_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        c.execute('''
            INSERT INTO booker_suggestions (
                suggestion_id, category, priority, headline, rationale, options_json,
                projections_json, context_json, status, response_reason, counter_pitch,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sid,
            p.get('category', 'creative-spark'),
            priority,
            p.get('headline', 'New suggestion'),
            p.get('rationale', ''),
            json.dumps(p.get('options', [])),
            json.dumps(p.get('projections', {})),
            json.dumps(p.get('context', {})),
            status,
            p.get('response_reason'),
            p.get('counter_pitch'),
            now,
            now,
        ))
        db.conn.commit()
        row = c.execute('SELECT * FROM booker_suggestions WHERE suggestion_id = ?', (sid,)).fetchone()
        return jsonify(_row_to_suggestion(row)), 201

    status = request.args.get('status')
    query = 'SELECT * FROM booker_suggestions'
    params = []
    if status:
        query += ' WHERE status = ?'
        params.append(status)
    query += ' ORDER BY created_at DESC'
    rows = c.execute(query, params).fetchall()
    return jsonify({'total': len(rows), 'suggestions': [_row_to_suggestion(r) for r in rows]})


@booker_bp.route('/api/booker/suggestions/<suggestion_id>/respond', methods=['POST'])
def respond_suggestion(suggestion_id):
    db = get_database()
    _ensure_tables(db)
    c = db.conn.cursor()
    p = request.get_json(silent=True) or {}
    action = str(p.get('action', '')).lower()
    mapping = {'accept': 'accepted', 'reject': 'rejected', 'modify': 'modified', 'pin': 'pinned', 'dismiss': 'dismissed'}
    if action not in mapping:
        return jsonify({'error': 'Invalid action'}), 400
    new_status = mapping[action]
    c.execute('''
        UPDATE booker_suggestions
        SET status = ?, response_reason = ?, counter_pitch = ?, updated_at = ?
        WHERE suggestion_id = ?
    ''', (new_status, p.get('reason'), p.get('counter_pitch'), _now_iso(), suggestion_id))
    if c.rowcount == 0:
        return jsonify({'error': 'Suggestion not found'}), 404

    title = p.get('notebook_title') or f"{action.title()}: {suggestion_id}"
    body = p.get('notebook_body') or p.get('note') or 'Player response captured.'
    c.execute('''
        INSERT INTO creative_notebook_entries (entry_id, suggestion_id, title, body, tag, pinned, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (f"nb_{uuid.uuid4().hex[:12]}", suggestion_id, title, body, p.get('tag'), 1 if new_status == 'pinned' else 0, _now_iso()))
    db.conn.commit()
    return jsonify({'success': True, 'status': new_status})


@booker_bp.route('/api/booker/notebook', methods=['GET'])
def notebook():
    db = get_database()
    _ensure_tables(db)
    c = db.conn.cursor()
    rows = c.execute('SELECT * FROM creative_notebook_entries ORDER BY created_at DESC').fetchall()
    return jsonify({'total': len(rows), 'entries': [dict(r) for r in rows]})
