from flask import Blueprint, request, jsonify
from models import db, Player
from datetime import datetime

players_bp = Blueprint('players', __name__)


@players_bp.route('', methods=['GET'])
def get_players():
    """Get all players, optionally filtered by club_id or subgroup_id"""
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    
    query = Player.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    if subgroup_id:
        query = query.filter_by(subgroup_id=subgroup_id)
    
    players = query.order_by(Player.created_at.desc()).all()
    return jsonify([player.to_dict() for player in players])


@players_bp.route('/<player_id>', methods=['GET'])
def get_player(player_id):
    """Get a single player by ID"""
    player = Player.query.get_or_404(player_id)
    return jsonify(player.to_dict())


@players_bp.route('/qr/<qr_code>', methods=['GET'])
def get_player_by_qr(qr_code):
    """Get a player by QR code"""
    # QR code format: CLUB_PLAYER_{id}
    if not qr_code.startswith('CLUB_PLAYER_'):
        return jsonify({'error': 'Invalid QR code format'}), 400
    
    player_id = qr_code.replace('CLUB_PLAYER_', '')
    player = Player.query.get_or_404(player_id)
    return jsonify(player.to_dict())


@players_bp.route('/search', methods=['GET'])
def search_players():
    """Search players by name or ID"""
    query_str = request.args.get('q', '').lower()
    club_id = request.args.get('club_id')
    
    query = Player.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    
    players = query.all()
    
    # Filter by search query
    if query_str:
        players = [p for p in players if 
                   query_str in p.full_name.lower() or 
                   query_str in p.id.lower()]
    
    return jsonify([player.to_dict() for player in players])


@players_bp.route('/filter', methods=['GET'])
def filter_players():
    """Filter players by payment status"""
    payment_status = request.args.get('payment_status')
    club_id = request.args.get('club_id')
    
    query = Player.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    if payment_status:
        query = query.filter_by(payment_status=payment_status)
    
    players = query.order_by(Player.created_at.desc()).all()
    return jsonify([player.to_dict() for player in players])


@players_bp.route('', methods=['POST'])
def create_player():
    """Create a new player"""
    data = request.get_json()
    
    if not data or not data.get('fullName'):
        return jsonify({'error': 'الاسم الكامل مطلوب'}), 400
    
    player = Player(
        full_name=data['fullName'],
        date_of_birth=datetime.fromisoformat(data['dateOfBirth']).date() if data.get('dateOfBirth') else None,
        payment_status=data.get('paymentStatus', 'unpaid'),
        amount_due=data.get('amountDue'),
        notes=data.get('notes'),
        image_url=data.get('imageUrl'),
        club_id=data.get('clubId'),
        subgroup_id=data.get('subgroupId'),
        pin=data.get('pin'),
    )
    
    db.session.add(player)
    db.session.commit()
    
    return jsonify(player.to_dict()), 201


@players_bp.route('/<player_id>', methods=['PUT'])
def update_player(player_id):
    """Update an existing player"""
    player = Player.query.get_or_404(player_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'لا توجد بيانات'}), 400
    
    if 'fullName' in data:
        player.full_name = data['fullName']
    if 'dateOfBirth' in data:
        player.date_of_birth = datetime.fromisoformat(data['dateOfBirth']).date() if data['dateOfBirth'] else None
    if 'paymentStatus' in data:
        player.payment_status = data['paymentStatus']
    if 'amountDue' in data:
        player.amount_due = data['amountDue']
    if 'notes' in data:
        player.notes = data['notes']
    if 'imageUrl' in data:
        player.image_url = data['imageUrl']
    if 'clubId' in data:
        player.club_id = data['clubId']
    if 'subgroupId' in data:
        player.subgroup_id = data['subgroupId']
    if 'pin' in data:
        player.pin = data['pin']
    
    player.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify(player.to_dict(include_match_stats=True))


@players_bp.route('/<player_id>', methods=['DELETE'])
def delete_player(player_id):
    """Delete a player"""
    player = Player.query.get_or_404(player_id)
    
    db.session.delete(player)
    db.session.commit()
    
    return jsonify({'message': 'Player deleted successfully'})


@players_bp.route('/stats', methods=['GET'])
def get_stats():
    """Get player statistics"""
    club_id = request.args.get('club_id')
    
    query = Player.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    
    players = query.all()
    total = len(players)
    paid = sum(1 for p in players if p.payment_status == 'paid')
    unpaid = total - paid
    
    return jsonify({
        'total': total,
        'paid': paid,
        'unpaid': unpaid,
    })
