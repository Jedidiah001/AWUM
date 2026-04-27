"""
Roster Routes - Wrestler Management
"""

from flask import Blueprint, jsonify, request, current_app

roster_bp = Blueprint('roster', __name__)


def get_universe():
    return current_app.config['UNIVERSE']


@roster_bp.route('/api/roster')
def api_get_roster():
    universe = get_universe()
    
    brand = request.args.get('brand')
    alignment = request.args.get('alignment')
    role = request.args.get('role')
    gender = request.args.get('gender')
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    wrestlers = universe.wrestlers
    
    if active_only:
        wrestlers = [w for w in wrestlers if not w.is_retired]
    
    if brand:
        wrestlers = [w for w in wrestlers if w.primary_brand == brand]
    
    if alignment:
        wrestlers = [w for w in wrestlers if w.alignment == alignment]
    
    if role:
        wrestlers = [w for w in wrestlers if w.role == role]
    
    if gender:
        wrestlers = [w for w in wrestlers if w.gender == gender]
    
    return jsonify({
        'total': len(wrestlers),
        'wrestlers': [w.to_dict() for w in wrestlers]
    })


@roster_bp.route('/api/roster/<wrestler_id>')
def api_get_wrestler(wrestler_id):
    universe = get_universe()
    wrestler = universe.get_wrestler_by_id(wrestler_id)
    
    if not wrestler:
        return jsonify({'error': 'Wrestler not found'}), 404
    
    return jsonify(wrestler.to_dict())


@roster_bp.route('/api/stats/roster-summary')
def api_roster_summary():
    universe = get_universe()
    
    summary = {
        'total_wrestlers': len(universe.wrestlers),
        'active_wrestlers': len(universe.get_active_wrestlers()),
        'retired_wrestlers': len(universe.retired_wrestlers),
        'by_brand': {},
        'by_role': {},
        'by_alignment': {},
        'by_gender': {},
        'major_superstars': len([w for w in universe.wrestlers if w.is_major_superstar]),
        'injured_wrestlers': len([w for w in universe.wrestlers if w.is_injured]),
        'contracts_expiring_soon': len([w for w in universe.wrestlers if w.contract_expires_soon])
    }
    
    for brand in ['ROC Alpha', 'ROC Velocity', 'ROC Vanguard']:
        summary['by_brand'][brand] = len([w for w in universe.wrestlers if w.primary_brand == brand and not w.is_retired])
    
    for role in ['Main Event', 'Upper Midcard', 'Midcard', 'Lower Midcard', 'Jobber']:
        summary['by_role'][role] = len([w for w in universe.wrestlers if w.role == role and not w.is_retired])
    
    for alignment in ['Face', 'Heel', 'Tweener']:
        summary['by_alignment'][alignment] = len([w for w in universe.wrestlers if w.alignment == alignment and not w.is_retired])
    
    for gender in ['Male', 'Female']:
        summary['by_gender'][gender] = len([w for w in universe.wrestlers if w.gender == gender and not w.is_retired])
    
    return jsonify(summary)