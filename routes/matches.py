from flask import Blueprint, request, jsonify
from models import db, Match, Player, Club
from datetime import datetime

matches_bp = Blueprint('matches', __name__)


@matches_bp.route('/', methods=['GET'])
def get_matches():
    """Get all matches, optionally filtered by club_id or subgroup_id"""
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    
    query = Match.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    if subgroup_id:
        query = query.filter_by(subgroup_id=subgroup_id)
    
    matches = query.order_by(Match.match_date.desc()).all()
    return jsonify([m.to_dict(include_players=True) for m in matches])


@matches_bp.route('/<match_id>', methods=['GET'])
def get_match(match_id):
    """Get a specific match by ID"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    return jsonify(match.to_dict(include_players=True))


@matches_bp.route('/', methods=['POST'])
def create_match():
    """Create a new match"""
    data = request.get_json()
    
    if not data.get('clubId'):
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    
    if not data.get('matchType'):
        return jsonify({'error': 'نوع المباراة مطلوب (ودي أو رسمي)'}), 400
    
    if not data.get('opponentName'):
        return jsonify({'error': 'اسم الفريق المنافس مطلوب'}), 400
    
    if not data.get('matchDate'):
        return jsonify({'error': 'تاريخ المباراة مطلوب'}), 400
    
    # Verify club exists
    club = Club.query.get(data['clubId'])
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    match = Match(
        club_id=data['clubId'],
        match_type=data['matchType'],
        opponent_name=data['opponentName'],
        match_date=datetime.fromisoformat(data['matchDate']).date(),
        our_score=data.get('ourScore'),
        opponent_score=data.get('opponentScore'),
        notes=data.get('notes'),
        subgroup_id=data.get('subgroupId')
    )
    
    # Add players to match
    player_ids = data.get('playerIds', [])
    if player_ids:
        players = Player.query.filter(Player.id.in_(player_ids)).all()
        for player in players:
            match.players.append(player)
    
    db.session.add(match)
    db.session.commit()
    
    return jsonify(match.to_dict(include_players=True)), 201


@matches_bp.route('/<match_id>', methods=['PUT'])
def update_match(match_id):
    """Update a match"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    
    data = request.get_json()
    
    if 'matchType' in data:
        match.match_type = data['matchType']
    if 'opponentName' in data:
        match.opponent_name = data['opponentName']
    if 'matchDate' in data:
        match.match_date = datetime.fromisoformat(data['matchDate']).date()
    if 'ourScore' in data:
        match.our_score = data['ourScore']
    if 'opponentScore' in data:
        match.opponent_score = data['opponentScore']
    if 'notes' in data:
        match.notes = data['notes']
    if 'subgroupId' in data:
        match.subgroup_id = data['subgroupId']
    
    # Update players if provided
    if 'playerIds' in data:
        # Clear existing players
        match.players = []
        # Add new players
        player_ids = data['playerIds']
        if player_ids:
            players = Player.query.filter(Player.id.in_(player_ids)).all()
            for player in players:
                match.players.append(player)
    
    db.session.commit()
    return jsonify(match.to_dict(include_players=True))


@matches_bp.route('/<match_id>', methods=['DELETE'])
def delete_match(match_id):
    """Delete a match"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    
    db.session.delete(match)
    db.session.commit()
    
    return jsonify({'message': 'تم حذف المباراة بنجاح'})


@matches_bp.route('/club/<club_id>', methods=['GET'])
def get_club_matches(club_id):
    """Get all matches for a specific club"""
    club = Club.query.get(club_id)
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    matches = Match.query.filter_by(club_id=club_id).order_by(Match.match_date.desc()).all()
    return jsonify([m.to_dict(include_players=True) for m in matches])


@matches_bp.route('/player/<player_id>/stats', methods=['GET'])
def get_player_match_stats(player_id):
    """Get match statistics for a specific player"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    return jsonify(player.get_match_stats())


@matches_bp.route('/player/<player_id>', methods=['GET'])
def get_player_matches(player_id):
    """Get all matches a player participated in"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    matches = player.matches.order_by(Match.match_date.desc()).all()
    return jsonify([m.to_dict() for m in matches])
