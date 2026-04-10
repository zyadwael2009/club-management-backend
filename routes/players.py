from flask import Blueprint, request, jsonify, session
from models import db, Player, User, Coach
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime

players_bp = Blueprint('players', __name__)


@players_bp.route('', methods=['GET'])
@login_required
def get_players():
    """Get all players (filtered by club for admin, all for superadmin)"""
    current_user = User.query.get(session['user_id'])
    
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    
    query = Player.query
    
    # Role-based filtering
    if current_user.role == 'admin':
        # Admin sees only their club's players
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        # Coach sees only their club's players
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'player':
        # Player sees only themselves
        query = query.filter_by(id=current_user.player_id)
    else:
        # Superadmin can filter by club
        if club_id:
            query = query.filter_by(club_id=club_id)
    
    if subgroup_id:
        query = query.filter_by(subgroup_id=subgroup_id)
    
    players = query.order_by(Player.created_at.desc()).all()
    return jsonify([player.to_dict() for player in players])


@players_bp.route('/<player_id>', methods=['GET'])
@login_required
def get_player(player_id):
    """Get a single player by ID"""
    player = Player.query.get_or_404(player_id)
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player' and player.id != current_user.player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify(player.to_dict())


@players_bp.route('/qr/<qr_code>', methods=['GET'])
def get_player_by_qr(qr_code):
    """Get a player by QR code"""
    # QR code format: CLUB_PLAYER_{id} (or legacy CLUB_MGMT_{id})
    if not qr_code.startswith('CLUB_PLAYER_') and not qr_code.startswith('CLUB_MGMT_'):
        return jsonify({'error': 'Invalid QR code format'}), 400

    player_id = (
        qr_code.replace('CLUB_PLAYER_', '')
        if qr_code.startswith('CLUB_PLAYER_')
        else qr_code.replace('CLUB_MGMT_', '')
    )
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
@admin_or_superadmin_required
def create_player():
    """Create a new player (admin/superadmin only)"""
    current_user = User.query.get(session['user_id'])
    data = request.get_json()
    
    if not data or not data.get('fullName'):
        return jsonify({'error': 'الاسم الكامل مطلوب'}), 400
    
    club_id = data.get('clubId')
    
    # Admin can only create players for their club
    if current_user.role == 'admin' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة لاعبين لهذا النادي'}), 403
    
    # Check if username is provided and unique
    username = data.get('username')
    password = data.get('password')
    
    if username:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
        
        if not password or len(password) < 4:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    
    try:
        player = Player(
            full_name=data['fullName'],
            date_of_birth=datetime.fromisoformat(data['dateOfBirth']).date() if data.get('dateOfBirth') else None,
            payment_status=data.get('paymentStatus', 'unpaid'),
            amount_due=data.get('amountDue'),
            notes=data.get('notes'),
            phone_number=data.get('phoneNumber'),
            image_url=data.get('imageUrl'),
            club_id=club_id,
            subgroup_id=data.get('subgroupId'),
            pin=data.get('pin'),
        )
        
        db.session.add(player)
        db.session.flush()  # Get the player ID
        
        # Create user if username provided
        if username:
            user = User(
                username=username,
                role='player',
                club_id=club_id,
                player_id=player.id
            )
            user.set_password(password)
            db.session.add(user)
        
        db.session.commit()
        return jsonify(player.to_dict()), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء اللاعب: {str(e)}'}), 500


@players_bp.route('/<player_id>', methods=['PUT'])
@admin_or_superadmin_required
def update_player(player_id):
    """Update an existing player (admin/superadmin only)"""
    player = Player.query.get_or_404(player_id)
    current_user = User.query.get(session['user_id'])
    
    # Admin can only update their club's players
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا اللاعب'}), 403
    
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
    if 'phoneNumber' in data:
        player.phone_number = data['phoneNumber']
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
@admin_or_superadmin_required
def delete_player(player_id):
    """Delete a player (admin/superadmin only)"""
    player = Player.query.get_or_404(player_id)
    current_user = User.query.get(session['user_id'])
    
    # Admin can only delete their club's players
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا اللاعب'}), 403
    
    try:
        # Delete associated user if exists
        user = User.query.filter_by(player_id=player_id).first()
        if user:
            db.session.delete(user)
        
        db.session.delete(player)
        db.session.commit()
        
        return jsonify({'message': 'تم حذف اللاعب بنجاح'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف اللاعب: {str(e)}'}), 500


@players_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """Get player statistics (filtered by role)"""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')
    
    query = Player.query
    
    # Role-based filtering
    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role != 'superadmin':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    else:
        # Superadmin can filter by club
        if club_id:
            query = query.filter_by(club_id=club_id)
    if club_id:
        query = query.filter_by(club_id=club_id)
    
    players = query.all()
    total = len(players)
    paid = sum(1 for p in players if p.payment_status == 'paid')
    unpaid = total - paid

    coach_query = Coach.query
    if current_user.role in ['admin', 'coach'] and current_user.club_id:
        coach_query = coach_query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'superadmin' and club_id:
        coach_query = coach_query.filter_by(club_id=club_id)
    total_coaches = coach_query.count()
    
    return jsonify({
        'total': total,
        'paid': paid,
        'unpaid': unpaid,
        'totalCoaches': total_coaches,
    })
