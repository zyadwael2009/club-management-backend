from flask import Blueprint, request, jsonify, session
from models import db, Club, User, Player, Subgroup, Training, CheckIn, PlayerPayment, Season
from routes.auth import superadmin_required, login_required
from season_context import get_effective_season_id
from datetime import datetime

clubs_bp = Blueprint('clubs', __name__)


@clubs_bp.route('', methods=['GET'])
@login_required
def get_clubs():
    """Get all clubs (superadmin sees all, admin sees only their club)"""
    current_user = User.query.get(session['user_id'])
    
    if current_user.role == 'superadmin':
        # Superadmin sees all clubs
        clubs = Club.query.order_by(Club.created_at.desc()).all()
    elif current_user.role == 'admin':
        # Admin sees only their club
        clubs = Club.query.filter_by(id=current_user.club_id).all()
    else:
        # Coach/Player shouldn't access club list directly
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify([club.to_dict() for club in clubs])


@clubs_bp.route('/<club_id>', methods=['GET'])
@login_required
def get_club(club_id):
    """Get a single club by ID"""
    club = Club.query.get_or_404(club_id)
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and club.id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify(club.to_dict())


@clubs_bp.route('', methods=['POST'])
@superadmin_required
def create_club():
    """Create a new club with admin user (superadmin only)"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'error': 'اسم النادي مطلوب'}), 400
    
    # Validate admin username and password
    admin_username = data.get('adminUsername')
    admin_password = data.get('adminPassword')
    
    if not admin_username or not admin_password:
        return jsonify({'error': 'اسم المستخدم وكلمة المرور للمدير مطلوبان'}), 400
    
    # Check if username already exists
    existing_user = User.query.filter_by(username=admin_username).first()
    if existing_user:
        return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
    
    if len(admin_password) < 4:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    
    try:
        due_date = None
        if data.get('dueDate'):
            due_date = datetime.fromisoformat(data['dueDate']).date()
        monthly_amount = data.get('monthlyAmount')
        monthly_amount = float(monthly_amount) if monthly_amount not in [None, ''] else None
        if monthly_amount is not None and monthly_amount < 0:
            return jsonify({'error': 'القسط الشهري للنادي لا يمكن أن يكون سالباً'}), 400

        # Create club
        club = Club(
            name=data['name'],
            primary_color=data.get('primaryColor', '#2196F3'),
            secondary_color=data.get('secondaryColor', '#FFC107'),
            logo_url=data.get('logoUrl'),
            due_date=due_date,
            monthly_amount=monthly_amount,
            is_active=True,
            deactivated_at=None,
        )
        db.session.add(club)
        db.session.flush()  # Get the club ID
        
        # Create admin user for this club
        admin_user = User(
            username=admin_username,
            role='admin',
            club_id=club.id
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)
        
        db.session.commit()
        
        return jsonify({
            'club': club.to_dict(),
            'admin': admin_user.to_dict()
        }), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء النادي: {str(e)}'}), 500


@clubs_bp.route('/<club_id>', methods=['PUT'])
@superadmin_required
def update_club(club_id):
    """Update an existing club"""
    club = Club.query.get_or_404(club_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    if 'name' in data:
        club.name = data['name']
    if 'primaryColor' in data:
        club.primary_color = data['primaryColor']
    if 'secondaryColor' in data:
        club.secondary_color = data['secondaryColor']
    if 'logoUrl' in data:
        club.logo_url = data['logoUrl']
    if 'dueDate' in data:
        club.due_date = datetime.fromisoformat(data['dueDate']).date() if data['dueDate'] else None
    if 'monthlyAmount' in data:
        monthly_amount = data['monthlyAmount']
        if monthly_amount in ['', None]:
            club.monthly_amount = None
        else:
            monthly_amount = float(monthly_amount)
            if monthly_amount < 0:
                return jsonify({'error': 'القسط الشهري للنادي لا يمكن أن يكون سالباً'}), 400
            club.monthly_amount = monthly_amount
    if 'isActive' in data:
        club.is_active = bool(data['isActive'])
        if club.is_active:
            club.deactivated_at = None
    
    club.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify(club.to_dict())


@clubs_bp.route('/<club_id>', methods=['DELETE'])
@superadmin_required
def delete_club(club_id):
    """Delete a club and all associated data"""
    club = Club.query.get_or_404(club_id)
    
    db.session.delete(club)
    db.session.commit()
    
    return jsonify({'message': 'Club deleted successfully'})


@clubs_bp.route('/<club_id>/deactivate', methods=['PUT'])
@superadmin_required
def deactivate_club_accounts(club_id):
    club = Club.query.get_or_404(club_id)
    users = User.query.filter_by(club_id=club_id).all()
    for user in users:
        if user.role != 'superadmin':
            user.is_active = False

    club.is_active = False
    club.deactivated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'تم تعطيل جميع حسابات النادي', 'club': club.to_dict()}), 200


@clubs_bp.route('/<club_id>/reactivate', methods=['PUT'])
@superadmin_required
def reactivate_club_accounts(club_id):
    club = Club.query.get_or_404(club_id)
    data = request.get_json() or {}

    due_date = data.get('dueDate')
    if due_date:
        club.due_date = datetime.fromisoformat(due_date).date()

    users = User.query.filter_by(club_id=club_id).all()
    for user in users:
        if user.role != 'superadmin':
            user.is_active = True

    club.is_active = True
    club.deactivated_at = None
    db.session.commit()
    return jsonify({'message': 'تم إعادة تفعيل حسابات النادي', 'club': club.to_dict()}), 200


@clubs_bp.route('/meta/data-presence', methods=['GET'])
@login_required
def get_clubs_data_presence():
    """Return record counts by club to help superadmin trace hidden-by-scope data."""
    current_user = User.query.get(session['user_id'])
    if current_user.role != 'superadmin':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    clubs = Club.query.order_by(Club.created_at.desc()).all()
    current_season = Season.query.filter_by(is_current=True).order_by(Season.updated_at.desc()).first()
    season_id = get_effective_season_id(default_to_current=True)
    result = []
    for club in clubs:
        player_count = Player.query.filter_by(club_id=club.id).count()
        subgroup_count = Subgroup.query.filter_by(club_id=club.id).count()

        trainings_query = Training.query.filter_by(club_id=club.id)
        if season_id:
            trainings_query = trainings_query.filter_by(season_id=season_id)
        training_count = trainings_query.count()

        checkins_query = CheckIn.query.filter_by(club_id=club.id)
        if season_id:
            checkins_query = checkins_query.filter_by(season_id=season_id)
        checkin_count = checkins_query.count()

        payments_query = (
            db.session.query(PlayerPayment)
            .join(Player, PlayerPayment.player_id == Player.id)
            .filter(Player.club_id == club.id)
        )
        if season_id:
            payments_query = payments_query.filter(PlayerPayment.season_id == season_id)
        payment_count = (
            payments_query.count()
        )

        result.append({
            'clubId': club.id,
            'clubName': club.name,
            'isActive': bool(club.is_active),
            'currentSeasonId': current_season.id if current_season else None,
            'appliedSeasonId': season_id,
            'players': player_count,
            'subgroups': subgroup_count,
            'trainings': training_count,
            'checkins': checkin_count,
            'playerPayments': payment_count,
            'hasOperationalData': any([
                player_count > 0,
                subgroup_count > 0,
                training_count > 0,
                checkin_count > 0,
                payment_count > 0,
            ]),
        })

    return jsonify(result), 200
