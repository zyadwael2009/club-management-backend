from flask import Blueprint, request, jsonify
from models import db, CheckIn, Player
from datetime import datetime

checkins_bp = Blueprint('checkins', __name__)


@checkins_bp.route('', methods=['GET'])
def get_checkins():
    """Get all check-ins, optionally filtered by club_id"""
    club_id = request.args.get('club_id')
    limit = request.args.get('limit', 50, type=int)
    
    query = CheckIn.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    
    checkins = query.order_by(CheckIn.timestamp.desc()).limit(limit).all()
    return jsonify([checkin.to_dict() for checkin in checkins])


@checkins_bp.route('/player/<player_id>', methods=['GET'])
def get_player_checkins(player_id):
    """Get check-ins for a specific player"""
    limit = request.args.get('limit', 20, type=int)
    
    checkins = CheckIn.query.filter_by(player_id=player_id)\
        .order_by(CheckIn.timestamp.desc())\
        .limit(limit).all()
    
    return jsonify([checkin.to_dict() for checkin in checkins])


@checkins_bp.route('', methods=['POST'])
def create_checkin():
    """Create a new check-in"""
    data = request.get_json()
    
    if not data or not data.get('playerId'):
        return jsonify({'error': 'Player ID is required'}), 400
    
    # Get player to create snapshot
    player = Player.query.get(data['playerId'])
    if not player:
        return jsonify({'error': 'Player not found'}), 404
    
    checkin = CheckIn(
        player_id=data['playerId'],
        club_id=data.get('clubId') or player.club_id,
        player_name=player.full_name,
        player_payment_status=player.payment_status,
    )
    
    db.session.add(checkin)
    db.session.commit()
    
    return jsonify(checkin.to_dict()), 201
