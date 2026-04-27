"""
Show Routes - Show Simulation & History
"""

from flask import Blueprint, jsonify, request, current_app
import traceback

show_bp = Blueprint('show', __name__)


def get_database():
    return current_app.config['DATABASE']


def get_universe():
    return current_app.config['UNIVERSE']


def get_injury_manager():
    return current_app.config.get('INJURY_MANAGER')


@show_bp.route('/api/show/simulate', methods=['POST'])
def api_simulate_show():
    database = get_database()
    universe = get_universe()
    injury_manager = get_injury_manager()
    
    try:
        from simulation.show_sim import show_simulator
        from models.show import ShowDraft
        
        data = request.get_json()
        
        show_draft = ShowDraft.from_dict(data)
        
        print(f"\n{'='*60}")
        print(f"📡 API: Received show simulation request")
        print(f"   Show: {show_draft.show_name}")
        print(f"   Year {show_draft.year}, Week {show_draft.week}")
        print(f"   Matches: {len(show_draft.matches)}")
        print(f"{'='*60}\n")
        
        show_result = show_simulator.simulate_show(show_draft, universe)

        if injury_manager:
            print("\n🏥 Processing injury recovery...")
            recovery_updates = injury_manager.process_weekly_recovery(
                universe.wrestlers,
                show_draft.year,
                show_draft.week
            )
            
            for update in recovery_updates:
                if update['status'] == 'recovered':
                    show_result.add_event(
                        'injury_recovery',
                        f"✅ {update['wrestler_name']} has recovered from injury!"
                    )
                elif update['status'] == 'milestone':
                    show_result.add_event(
                        'rehab_milestone',
                        f"🏥 {update['message']}"
                    )
            
            print(f"   {len(recovery_updates)} recovery updates processed")
        
        if hasattr(show_result, 'injury_angles_needed'):
            print(f"\n📝 Injury angles needed for next week: {len(show_result.injury_angles_needed)}")
        
        print("\n💾 Saving results to database...")
        
        database.save_show_result(show_result)
        
        universe.save_all()
        
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
        
        print(f"✅ All data saved successfully!")
        print(f"   Advanced to: Year {next_show.year if next_show else '?'}, Week {next_show.week if next_show else '?'}")
        print()
        
        return jsonify({
            'success': True,
            'show_result': show_result.to_dict()
        })
    
    except Exception as e:
        error_trace = traceback.format_exc()
        
        print("\n" + "="*60)
        print("❌ SHOW SIMULATION ERROR")
        print("="*60)
        print(error_trace)
        print("="*60 + "\n")
        
        try:
            database.conn.rollback()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': error_trace
        }), 500


@show_bp.route('/api/show/history')
def api_show_history():
    database = get_database()
    
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    try:
        history = database.get_show_history(limit=limit, offset=offset)
        
        cursor = database.conn.cursor()
        cursor.execute('SELECT COUNT(*) as total FROM show_history')
        total = cursor.fetchone()['total']
        
        return jsonify({
            'success': True,
            'total': total,
            'shows': history
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'shows': []
        }), 500


@show_bp.route('/api/match/history')
def api_match_history():
    database = get_database()
    
    wrestler_id = request.args.get('wrestler_id')
    limit = request.args.get('limit', 20, type=int)
    
    matches = database.get_match_history(wrestler_id=wrestler_id, limit=limit)
    
    return jsonify({
        'total': len(matches),
        'matches': matches
    })
