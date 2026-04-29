"""
Booking Routes - Enhanced Show Card Management with Gender Separation
Adapted to work with custom Database class (not Flask-SQLAlchemy)
"""

from flask import Blueprint, request, jsonify, current_app
import json
import uuid
from datetime import datetime

from models.show import ShowDraft, SegmentDraft
from models.match import MatchDraft
from services.creative_director import CreativeDirector
from services.production_planner import ProductionPlanner

booking_bp = Blueprint('booking', __name__, url_prefix='/api/booking')

# ============================================================================
# HELPER: Get Database from App Config
# ============================================================================

def get_database():
    """Get database instance from Flask app config"""
    return current_app.config.get('DATABASE')


def get_universe():
    """Get universe state from app config"""
    return current_app.config.get('UNIVERSE')

# ============================================================================
# GENERATE SHOW CARD WITH PRODUCTION PLAN
# ============================================================================

@booking_bp.route('/preview-next', methods=['GET'])
def preview_next_show():
    """
    Return a lightweight preview of the next scheduled show.
    Called by the Office view on load. Returns show name, type, brand, week and year.
    """
    try:
        database = get_database()
        universe = get_universe()
        game_state = database.get_game_state()
        scheduled_show = universe.calendar.get_current_show() if universe else None

        current_year = scheduled_show.year if scheduled_show else game_state.get('current_year', 2025)
        current_week = scheduled_show.week if scheduled_show else game_state.get('current_week', 1)
        current_brand = scheduled_show.brand if scheduled_show else game_state.get('current_brand', 'ROC Alpha')
        current_show_id = scheduled_show.show_id if scheduled_show else None
        current_show_name = scheduled_show.name if scheduled_show else f'{current_brand} Weekly TV'
        current_show_type = scheduled_show.show_type if scheduled_show else 'weekly_tv'

        # Try to find an existing draft first
        existing_draft = database.get_show_draft(current_show_id) if current_show_id else None
        if existing_draft:
            return jsonify({
                'success': True,
                'show_id': existing_draft.get('show_id', current_show_id),
                'show_name': existing_draft.get('show_name', current_show_name),
                'show_type': existing_draft.get('show_type', current_show_type),
                'brand': current_brand,
                'year': current_year,
                'week': current_week,
                'has_draft': True,
                'available_wrestlers': len(universe.get_wrestlers_by_brand(current_brand)) if universe else 0,
                'hot_feuds': len(universe.feud_manager.get_active_feuds()) if universe else 0,
            })

        return jsonify({
            'success': True,
            'show_id': current_show_id,
            'show_name': current_show_name,
            'show_type': current_show_type,
            'brand': current_brand,
            'year': current_year,
            'week': current_week,
            'has_draft': False,
            'available_wrestlers': len(universe.get_wrestlers_by_brand(current_brand)) if universe else 0,
            'hot_feuds': len(universe.feud_manager.get_active_feuds()) if universe else 0,
        })

    except Exception as e:
        print(f"Error in preview-next: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@booking_bp.route('/generate', methods=['POST'])
def generate_show_card():
    """
    Generate a complete show card with production plan
    Includes gender-separated matches and creative direction
    """
    try:
        database = get_database()
        universe = get_universe()
        data = request.get_json() or {}
        
        include_production_plan = data.get('include_production_plan', True)
        force_regenerate = data.get('force_regenerate', False)
        game_state = database.get_game_state()
        scheduled_show = universe.calendar.get_current_show() if universe else None
        current_brand = data.get('brand') or (scheduled_show.brand if scheduled_show else game_state.get('current_brand', 'ROC Alpha'))
        current_year = data.get('year') or (scheduled_show.year if scheduled_show else game_state.get('current_year', 2025))
        current_week = data.get('week') or (scheduled_show.week if scheduled_show else game_state.get('current_week', 1))
        current_show_id = data.get('show_id') or (scheduled_show.show_id if scheduled_show else str(uuid.uuid4()))
        
        # Check if there's already a show draft in progress
        if not force_regenerate:
            existing_draft = database.get_show_draft(current_show_id)
            if existing_draft:
                production_plan = database.get_production_plan(existing_draft['show_id'])
                return jsonify({
                    'success': True,
                    'show_draft': existing_draft,
                    'production_plan': production_plan
                })
        
        # Determine show type
        show_type = data.get('show_type') or (scheduled_show.show_type if scheduled_show else 'weekly_tv')
        is_ppv = show_type in ['minor_ppv', 'major_ppv']
        
        # Generate show name
        if data.get('show_name'):
            show_name = data['show_name']
        elif scheduled_show:
            show_name = scheduled_show.name
        elif is_ppv:
            show_name = f"{current_brand} PPV - Week {current_week}"
        else:
            show_name = f"{current_brand} Weekly TV - Week {current_week}"
        
        # Create new show draft
        show_draft = ShowDraft(
            show_id=current_show_id,
            show_name=show_name,
            brand=current_brand,
            show_type=show_type,
            is_ppv=is_ppv,
            year=current_year,
            week=current_week
        )
        
        # Initialize Production Planner
        planner = ProductionPlanner(show_draft)
        
        # Generate production plan
        production_plan = None
        if include_production_plan:
            production_plan = planner.generate_production_plan()
        
        # Initialize Creative Director
        director = CreativeDirector(show_draft)
        
        # Get active roster for this brand (FIXED: use primary_brand and is_retired)
        cursor = database.conn.cursor()
        cursor.execute('''
            SELECT * FROM wrestlers 
            WHERE primary_brand = ? AND is_retired = 0
        ''', (current_brand,))
        
        active_roster = []
        for row in cursor.fetchall():
            active_roster.append(dict(row))
        
        # Separate by gender (DB stores 'Male'/'Female' with capital first letter)
        male_roster = [w for w in active_roster if w.get('gender', '').lower() == 'male']
        female_roster = [w for w in active_roster if w.get('gender', '').lower() == 'female']
        
        # Get active feuds (FIXED: no brand column in feuds table)
        cursor.execute('''
            SELECT * FROM feuds 
            WHERE status = 'active'
        ''')
        
        active_feuds = []
        for row in cursor.fetchall():
            feud_dict = dict(row)
            # Parse JSON fields
            if 'participant_ids' in feud_dict and feud_dict['participant_ids']:
                try:
                    feud_dict['participant_ids'] = json.loads(feud_dict['participant_ids'])
                except:
                    feud_dict['participant_ids'] = []
            if 'participant_names' in feud_dict and feud_dict['participant_names']:
                try:
                    feud_dict['participant_names'] = json.loads(feud_dict['participant_names'])
                except:
                    feud_dict['participant_names'] = []
            active_feuds.append(feud_dict)
        
        # Generate matches based on production plan
        if production_plan:
            matches = director.generate_full_card_dict(
                male_roster,
                female_roster,
                active_feuds,
                production_plan
            )
        else:
            matches = director.generate_default_card_dict(
                male_roster,
                female_roster,
                active_feuds
            )
        
        # Build a wrestler lookup dict for name resolution
        wrestler_lookup = {w['id']: w for w in active_roster}
        
        def normalize_match_dict(m: dict, position: int) -> dict:
            """Convert CreativeDirector match dict to MatchDraft.from_dict format"""
            import uuid as _uuid
            match_type = m.get('match_type', 'singles')
            participants = m.get('participants', [])
            
            if match_type == 'tag':
                # participants is [[id, id], [id, id]]
                team_a_ids = participants[0] if len(participants) > 0 else []
                team_b_ids = participants[1] if len(participants) > 1 else []
            elif match_type == 'mixed_tag':
                # participants is [{'male': id, 'female': id}, {...}]
                team_a_ids = [participants[0]['male'], participants[0]['female']] if participants else []
                team_b_ids = [participants[1]['male'], participants[1]['female']] if len(participants) > 1 else []
            else:
                # singles / other: participants is [id, id]
                team_a_ids = [participants[0]] if len(participants) > 0 else []
                team_b_ids = [participants[1]] if len(participants) > 1 else []
            
            def get_names(ids):
                return [wrestler_lookup.get(wid, {}).get('name', wid) for wid in ids]
            
            return {
                'match_id': str(_uuid.uuid4()),
                'side_a': {
                    'wrestler_ids': team_a_ids,
                    'wrestler_names': get_names(team_a_ids),
                    'is_tag_team': len(team_a_ids) > 1
                },
                'side_b': {
                    'wrestler_ids': team_b_ids,
                    'wrestler_names': get_names(team_b_ids),
                    'is_tag_team': len(team_b_ids) > 1
                },
                'match_type': match_type,
                'is_title_match': m.get('is_title_match', False),
                'title_id': m.get('title_id'),
                'title_name': m.get('title_name'),
                'card_position': position,
                'booking_bias': m.get('booking_bias', 'even'),
                'importance': m.get('importance', 'normal'),
                'feud_id': m.get('feud_id'),
            }
        
        # Rebalance for wider roster showcase opportunities
        matches = _rebalance_matches_for_showcase(matches, active_roster, show_type)

        # Add matches to show draft
        for i, match_dict in enumerate(matches):
            normalized = normalize_match_dict(match_dict, i + 1)
            match = MatchDraft.from_dict(normalized)
            show_draft.add_match(match)
        
        # Generate segments
        segment_dicts = director.generate_segments_dict(active_feuds, matches)
        
        for seg_dict in segment_dicts:
            import uuid as _uuid
            normalized_seg = {
                'segment_id': str(_uuid.uuid4()),
                'segment_type': seg_dict.get('segment_type', 'promo'),
                'participants': [
                    {'id': pid, 'name': wrestler_lookup.get(pid, {}).get('name', pid)}
                    for pid in seg_dict.get('participants', []) if pid
                ],
                'duration_minutes': seg_dict.get('duration', seg_dict.get('duration_minutes', 5)),
                'card_position': seg_dict.get('position', seg_dict.get('card_position', 0)),
                'tone': seg_dict.get('tone', 'intense'),
                'feud_id': seg_dict.get('feud_id'),
            }
            segment = SegmentDraft.from_dict(normalized_seg)
            show_draft.add_segment(segment)
        
        # Save to database
        database.save_show_draft(show_draft, production_plan)
        
        return jsonify({
            'success': True,
            'show_draft': show_draft.to_dict(),
            'production_plan': production_plan,
            'match_count': len(matches),
            'segment_count': len(segment_dicts)
        })
        
    except Exception as e:
        print(f"Error generating show card: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# AUTO-GENERATE SEGMENTS
# ============================================================================

@booking_bp.route('/generate_segments', methods=['POST'])
def generate_segments():
    """Auto-generate segments based on feuds and match card"""
    try:
        database = get_database()
        data = request.get_json()
        
        show_draft_data = data.get('show_draft')
        
        if not show_draft_data:
            return jsonify({
                'success': False,
                'error': 'No show draft provided'
            }), 400
        
        # Reconstruct ShowDraft from dict
        show_draft = ShowDraft.from_dict(show_draft_data)
        
        # Get active feuds (no brand filter)
        cursor = database.conn.cursor()
        cursor.execute('''
            SELECT * FROM feuds 
            WHERE status = 'active'
        ''')
        
        active_feuds = []
        for row in cursor.fetchall():
            feud_dict = dict(row)
            # Parse JSON fields
            if 'participant_ids' in feud_dict and feud_dict['participant_ids']:
                try:
                    feud_dict['participant_ids'] = json.loads(feud_dict['participant_ids'])
                except:
                    feud_dict['participant_ids'] = []
            active_feuds.append(feud_dict)
        
        # Initialize Creative Director
        director = CreativeDirector(show_draft)
        
        # Generate segments
        match_dicts = [m.to_dict() for m in show_draft.matches]
        segment_dicts = director.generate_segments_dict(active_feuds, match_dicts)
        
        # Build wrestler lookup for name resolution
        cursor.execute('SELECT id, name FROM wrestlers WHERE is_retired = 0')
        wrestler_lookup = {row['id']: dict(row) for row in cursor.fetchall()}
        
        # Add to show draft with normalized dicts
        for seg_dict in segment_dicts:
            import uuid as _uuid
            normalized_seg = {
                'segment_id': str(_uuid.uuid4()),
                'segment_type': seg_dict.get('segment_type', 'promo'),
                'participants': [
                    {'id': pid, 'name': wrestler_lookup.get(pid, {}).get('name', pid)}
                    for pid in seg_dict.get('participants', []) if pid
                ],
                'duration_minutes': seg_dict.get('duration', seg_dict.get('duration_minutes', 5)),
                'card_position': seg_dict.get('position', seg_dict.get('card_position', 0)),
                'tone': seg_dict.get('tone', 'intense'),
                'feud_id': seg_dict.get('feud_id'),
            }
            segment = SegmentDraft.from_dict(normalized_seg)
            show_draft.add_segment(segment)
        
        # Update in database
        database.save_show_draft(show_draft)
        
        return jsonify({
            'success': True,
            'segments': [s.to_dict() for s in show_draft.segments]
        })
        
    except Exception as e:
        print(f"Error generating segments: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# RUN SHOW (SIMULATE)
# ============================================================================

@booking_bp.route('/run_show', methods=['POST'])
def run_show():
    """Simulate the show, generate results for all matches and segments"""
    try:
        database = get_database()
        universe = current_app.config.get('UNIVERSE')
        data = request.get_json()
        
        show_draft_data = data.get('show_draft')
        production_plan = data.get('production_plan')
        
        if not show_draft_data:
            return jsonify({
                'success': False,
                'error': 'No show draft provided'
            }), 400
        
        # Reconstruct ShowDraft from dict
        show_draft = ShowDraft.from_dict(show_draft_data)
        
        if len(show_draft.matches) < 3:
            return jsonify({
                'success': False,
                'error': 'Need at least 3 matches to run show'
            }), 400
        
        if not universe:
            return jsonify({
                'success': False,
                'error': 'Universe state is not available'
            }), 500

        # Import show simulator
        from simulation.show_sim import show_simulator
        
        # Simulate the show
        show_result = show_simulator.simulate_show(show_draft, universe)
        
        # Save show result to database
        database.save_show_result(show_result)

        # Persist all wrestler/title/feud changes created by the simulation
        universe.save_all()

        # Advance to the next scheduled show and sync game state to it
        universe.calendar.advance_to_next_show()
        next_show = universe.calendar.get_current_show()
        database.update_game_state(
            current_year=next_show.year if next_show else show_draft.year,
            current_week=next_show.week if next_show else show_draft.week,
            current_show_index=universe.calendar.current_show_index,
            balance=universe.balance,
            show_count=universe.show_count,
            current_brand=next_show.brand if next_show else show_draft.brand
        )
        
        # Clear the draft
        database.clear_show_draft(show_draft.show_id)

        
        # LegacyMania/Rumble Royale progression logic
        try:
            if (show_draft.show_name or '').lower() == 'rumble royale':
                match_lookup = {m.match_id: m for m in show_draft.matches}
                for result in show_result.match_results:
                    if getattr(result, 'match_type', '') != 'rumble':
                        continue
                    draft_match = match_lookup.get(getattr(result, 'match_id', None))
                    division = getattr(draft_match, 'gender_division', None) or 'male'
                    winner_id = getattr(result, 'winner_id', None)
                    if winner_id:
                        _award_rumble_opportunity(database, universe, winner_id, division, show_draft.year)

            if (show_draft.show_name or '').lower().startswith('legacymania'):
                # Brand transfer: title winners move to title's home brand
                for result in show_result.match_results:
                    if not getattr(result, 'is_title_match', False):
                        continue
                    title_id = getattr(result, 'title_id', None)
                    winner_id = getattr(result, 'winner_id', None)
                    if not title_id or not winner_id:
                        continue
                    title = next((t for t in universe.championships if getattr(t, 'id', None) == title_id), None)
                    wrestler = next((w for w in universe.wrestlers if getattr(w, 'id', None) == winner_id), None)
                    if title and wrestler and getattr(title, 'current_brand', None):
                        wrestler.current_brand = title.current_brand
                        wrestler.primary_brand = title.current_brand
                universe.save_all()
        except Exception as legacy_err:
            print(f'Legacy progression warning: {legacy_err}')

        show_result_data = show_result.to_dict()
        show_result_data['tv_rating'] = round(show_result.overall_rating * 1.5, 2)
        show_result_data['highlights'] = generate_show_highlights(show_result.match_results, production_plan)
        
        return jsonify({
            'success': True,
            'show_result': show_result_data
        })
        
    except Exception as e:
        print(f"Error running show: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500





def _rebalance_matches_for_showcase(matches: list, roster: list, show_type: str) -> list:
    """Ensure more roster variety so more talent gets TV opportunities."""
    if show_type != 'weekly_tv' or not matches:
        return matches

    used = set()
    for m in matches:
        for p in m.get('participants', []):
            if isinstance(p, str):
                used.add(p)
            elif isinstance(p, list):
                used.update([x for x in p if x])
            elif isinstance(p, dict):
                if p.get('male'): used.add(p['male'])
                if p.get('female'): used.add(p['female'])

    available = [w for w in roster if w.get('id') and w.get('id') not in used]
    if len(available) < 2:
        return matches

    a, b = available[0], available[1]
    showcase = {
        'match_type': 'singles',
        'participants': [a['id'], b['id']],
        'is_title_match': False,
        'booking_bias': 'even',
        'importance': 'normal'
    }

    replace_idx = None
    for i, m in enumerate(matches):
        if not m.get('is_title_match') and m.get('match_type') in ('singles', 'triple_threat', 'fatal_4way'):
            replace_idx = i
            break

    if replace_idx is not None:
        matches[replace_idx] = showcase
    else:
        matches.append(showcase)
    return matches

def _ensure_legacy_tables(database):
    c = database.conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rumble_title_opportunities (
            id TEXT PRIMARY KEY,
            year INTEGER NOT NULL,
            rumble_winner_id TEXT NOT NULL,
            rumble_winner_name TEXT NOT NULL,
            division TEXT NOT NULL,
            target_title_id TEXT,
            target_title_name TEXT,
            target_brand TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            storyline_text TEXT,
            created_at TEXT NOT NULL
        )
    """)
    database.conn.commit()


def _award_rumble_opportunity(database, universe, winner_id: str, division: str, year: int):
    import uuid as _uuid
    _ensure_legacy_tables(database)
    winner = next((w for w in universe.wrestlers if getattr(w, 'id', None) == winner_id), None)
    if not winner:
        return

    titles = [t for t in universe.championships if getattr(t, 'division', 'male') == division and not getattr(t, 'retired', False)]
    titles = sorted(titles, key=lambda t: getattr(t, 'prestige', 0), reverse=True)[:2]
    target_title = titles[0] if titles else None
    target_brand = getattr(target_title, 'current_brand', None) if target_title else None

    storyline = (
        f"After surviving the {division.title()} Royal Rumble at Rumble Royale, {getattr(winner,'name',winner_id)} "
        f"has earned a LegacyMania world title opportunity. The winner can challenge for a top title "
        f"on ROC Alpha or ROC Velocity, igniting cross-brand pressure heading into LegacyMania Night 1 and Night 2."
    )

    c = database.conn.cursor()
    c.execute(
        """
        INSERT INTO rumble_title_opportunities
        (id, year, rumble_winner_id, rumble_winner_name, division, target_title_id, target_title_name, target_brand, status, storyline_text, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            str(_uuid.uuid4()), year, winner_id, getattr(winner, 'name', winner_id), division,
            getattr(target_title, 'id', None), getattr(target_title, 'name', None), target_brand,
            'pending', storyline, datetime.now().isoformat()
        )
    )
    database.conn.commit()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_show_financials(show_type: str, overall_rating: float, 
                              production_plan: dict) -> tuple:
    """Calculate attendance and revenue"""
    
    # Base attendance
    base_attendance = {
        'weekly_tv': 5000,
        'minor_ppv': 10000,
        'major_ppv': 15000
    }.get(show_type, 5000)
    
    # Rating multiplier (0.0 - 5.0 -> 0.5 - 1.5)
    rating_multiplier = 0.5 + (overall_rating / 5.0)
    
    # Production plan bonus
    plan_multiplier = 1.0
    if production_plan:
        plan_multiplier += production_plan.get('theme_bonus_attendance_pct', 0.0)
    
    attendance = int(base_attendance * rating_multiplier * plan_multiplier)
    min_attendance = {
        'weekly_tv': 50000,
        'minor_ppv': 80000,
        'major_ppv': 150000
    }.get(show_type, 50000)
    attendance = max(min_attendance, attendance)
    
    # Revenue
    ticket_price = {
        'weekly_tv': 50,
        'minor_ppv': 75,
        'major_ppv': 100
    }.get(show_type, 50)
    try:
        cursor = database.conn.cursor()
        cursor.execute("SELECT show_ticket_prices_json FROM finance_settings WHERE id = 1")
        row = cursor.fetchone()
        if row and row[0]:
            prices = json.loads(row[0])
            ticket_price = int(prices.get(show_type, ticket_price))
    except Exception:
        pass
    
    revenue = attendance * ticket_price
    
    return attendance, revenue

def generate_show_highlights(match_results: list, production_plan: dict) -> list:
    """Generate narrative highlights from show results"""
    highlights = []

    def format_match_label(match_result) -> str:
        title_name = getattr(match_result, 'title_name', None)
        if title_name:
            return title_name

        special_match_type = getattr(match_result, 'special_match_type', None)
        if special_match_type:
            return special_match_type.replace('_', ' ').title()

        match_type = getattr(match_result, 'match_type', 'singles')
        return match_type.replace('_', ' ').title()
    
    # Find best match
    if match_results:
        best_match = max(match_results, key=lambda x: x.star_rating)
        if best_match.star_rating >= 4.0:
            highlights.append(
                f"⭐ Match of the Night: {best_match.match_type.replace('_', ' ').title()} "
                f"({best_match.star_rating:.2f} stars)"
            )
    
    # Title changes
    title_changes = [r for r in match_results if getattr(r, 'title_changed_hands', False)]
    for change in title_changes:
        highlights.append(
            f"🏆 NEW CHAMPION: Title changed hands in "
            f"{change.match_type.replace('_', ' ')}"
        )
    
    # Intergender matches
    intergender_matches = [r for r in match_results 
                          if r.match_type in ['mixed_tag', 'intergender_singles']]
    if intergender_matches:
        highlights.append(
            f"⚥ Historic intergender action with {len(intergender_matches)} "
            f"mixed match(es)"
        )
    
    # Production plan theme
    if production_plan and production_plan.get('theme') != 'standard':
        highlights.append(
            f"🎨 Special theme: {production_plan.get('theme_display_name', 'Special Event')}"
        )
    
    return highlights

def generate_show_highlights(match_results: list, production_plan: dict) -> list:
    """Generate narrative highlights from show results."""
    highlights = []

    def format_match_label(match_result) -> str:
        title_name = getattr(match_result, 'title_name', None)
        if title_name:
            return title_name

        special_match_type = getattr(match_result, 'special_match_type', None)
        if special_match_type:
            return special_match_type.replace('_', ' ').title()

        match_type = getattr(match_result, 'match_type', 'singles')
        return match_type.replace('_', ' ').title()

    if match_results:
        best_match = max(match_results, key=lambda result: result.star_rating)
        if best_match.star_rating >= 4.0:
            highlights.append(
                f"Match of the Night: {format_match_label(best_match)} "
                f"({best_match.star_rating:.2f} stars)"
            )

    title_changes = [result for result in match_results if getattr(result, 'title_changed_hands', False)]
    for change in title_changes:
        champion_name = (
            getattr(change, 'new_champion_name', None)
            or ', '.join(getattr(change, 'winner_names', []))
            or 'A new champion'
        )
        highlights.append(
            f"NEW CHAMPION: {champion_name} won the {format_match_label(change)}"
        )

    intergender_matches = [
        result for result in match_results
        if getattr(result, 'match_type', '') in ['mixed_tag', 'intergender_singles']
    ]
    if intergender_matches:
        highlights.append(
            f"Historic intergender action with {len(intergender_matches)} mixed match(es)"
        )

    if production_plan and production_plan.get('theme') != 'standard':
        highlights.append(
            f"Special theme: {production_plan.get('theme_display_name', 'Special Event')}"
        )

    return highlights


@booking_bp.route('/legacy/rumble-opportunities', methods=['GET'])
def get_rumble_opportunities():
    try:
        database = get_database()
        _ensure_legacy_tables(database)
        rows = database.conn.cursor().execute("SELECT * FROM rumble_title_opportunities ORDER BY created_at DESC LIMIT 50").fetchall()
        return jsonify({'success': True, 'opportunities': [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@booking_bp.route('/legacy/rumble-opportunities/<opp_id>/assign', methods=['POST'])
def assign_rumble_opportunity(opp_id):
    try:
        database = get_database()
        payload = request.get_json() or {}
        target_title_id = payload.get('target_title_id')
        target_title_name = payload.get('target_title_name')
        target_brand = payload.get('target_brand')
        legacy_night = payload.get('legacy_night')
        status = payload.get('status', 'assigned')

        _ensure_legacy_tables(database)
        database.conn.cursor().execute(
            """
            UPDATE rumble_title_opportunities
            SET target_title_id=?, target_title_name=?, target_brand=?, status=?, storyline_text = COALESCE(storyline_text,'') || ?, created_at=created_at
            WHERE id=?
            """,
            (target_title_id, target_title_name, target_brand, status, f' Assigned to {legacy_night} challenge.', opp_id)
        )
        database.conn.commit()
        return jsonify({'success': True, 'id': opp_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# GET/DELETE SHOW DRAFT
# ============================================================================

@booking_bp.route('/draft/<show_id>', methods=['GET'])
def get_show_draft(show_id):
    """Get a show draft with all matches and segments"""
    try:
        database = get_database()
        show_draft = database.get_show_draft(show_id)
        
        if not show_draft:
            return jsonify({
                'success': False,
                'error': 'Show draft not found'
            }), 404
        
        production_plan = database.get_production_plan(show_id)
        
        return jsonify({
            'success': True,
            'show': show_draft,
            'production_plan': production_plan
        })
        
    except Exception as e:
        print(f"Error getting show draft: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@booking_bp.route('/draft/<show_id>', methods=['DELETE'])
def delete_show_draft(show_id):
    """Delete a show draft"""
    try:
        database = get_database()
        success = database.clear_show_draft(show_id)
        
        if not success:
            return jsonify({
                'success': False,
                'error': 'Show draft not found'
            }), 404
        
        return jsonify({
            'success': True,
            'message': 'Show draft deleted'
        })
        
    except Exception as e:
        print(f"Error deleting show draft: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
