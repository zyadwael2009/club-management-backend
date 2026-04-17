from flask import Blueprint, request, jsonify, session
from models import db, Player, User, Coach, Subgroup, Club
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime, date
import calendar

players_bp = Blueprint('players', __name__)


def _add_one_month_keep_day(base_date, day_of_month):
    year = base_date.year
    month = base_date.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, max_day))


def _resolve_monthly_amount(subgroup, club, current_player_monthly=None):
    subgroup_monthly = float(subgroup.monthly_amount or 0.0) if subgroup else 0.0
    club_monthly = float(club.monthly_amount or 0.0) if club else 0.0
    current_monthly = float(current_player_monthly or 0.0)
    if subgroup_monthly > 0:
        return subgroup_monthly
    if club_monthly > 0:
        return club_monthly
    if current_monthly > 0:
        return current_monthly
    return 0.0


def _apply_player_renewals(player, today=None):
    current_date = today or date.today()
    subgroup = player.subgroup
    club = player.club
    resolved_monthly = _resolve_monthly_amount(subgroup, club, player.monthly_amount)
    if resolved_monthly <= 0:
        return False

    changed = False

    # Keep player monthly amount aligned with subgroup/club monthly settings.
    if float(player.monthly_amount or 0.0) != resolved_monthly:
        player.monthly_amount = resolved_monthly
        changed = True

    if not player.subscription_end_date:
        base_start = player.subscription_start_date or (player.created_at.date() if player.created_at else current_date)
        player.subscription_start_date = base_start
        player.subscription_end_date = _add_one_month_keep_day(base_start, base_start.day)
        changed = True
        return changed

    if player.subscription_end_date < current_date:
        if player.payment_status != 'unpaid':
            player.payment_status = 'unpaid'
            changed = True

        if float(player.amount_due or 0.0) <= 0:
            player.amount_due = resolved_monthly
            changed = True
        return changed

    return changed


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

    changed = False
    for player in players:
        if _apply_player_renewals(player):
            changed = True

    if changed:
        db.session.commit()

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
    
    if _apply_player_renewals(player):
        db.session.commit()

    return jsonify(player.to_dict())


@players_bp.route('/renewals/today', methods=['GET'])
@login_required
def get_today_renewals():
    """Return academy players that renew today with total renewal amount."""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')

    if current_user.role == 'admin':
        club_id = current_user.club_id
    elif current_user.role == 'coach':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'superadmin' and not club_id:
        return jsonify({'error': 'معرف النادي مطلوب'}), 400

    today = date.today()

    rows = (
        db.session.query(Player, Subgroup)
        .join(Subgroup, Player.subgroup_id == Subgroup.id)
        .filter(Player.club_id == club_id)
        .filter(Subgroup.subgroup_type == 'academy')
        .filter(Player.monthly_amount.isnot(None))
        .filter(Player.monthly_amount > 0)
        .filter(Player.subscription_end_date == today)
        .order_by(Player.full_name.asc())
        .all()
    )

    payload = []
    total = 0.0
    for player, subgroup in rows:
        total += float(player.monthly_amount or 0.0)
        payload.append({
            'id': player.id,
            'fullName': player.full_name,
            'monthlyAmount': float(player.monthly_amount or 0.0),
            'amountDue': float(player.amount_due or 0.0),
            'subgroupName': subgroup.name,
            'renewalDay': player.renewal_day,
            'subscriptionStartDate': player.subscription_start_date.isoformat() if player.subscription_start_date else None,
            'subscriptionEndDate': player.subscription_end_date.isoformat() if player.subscription_end_date else None,
        })

    return jsonify({
        'renewalDate': today.isoformat(),
        'playersCount': len(payload),
        'totalAmount': total,
        'players': payload,
    })


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
    username = (data.get('username') or '').strip()
    if not username:
        username = None
    password = data.get('password')
    
    if username:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
        
        if not password or len(password) < 4:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    
    subgroup_id = data.get('subgroupId')
    club = Club.query.get(club_id) if club_id else None
    if club_id and not club:
        return jsonify({'error': 'النادي غير موجود'}), 404

    subgroup = None
    if subgroup_id:
        subgroup = Subgroup.query.get(subgroup_id)
        if not subgroup:
            return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
        if subgroup.club_id != club_id:
            return jsonify({'error': 'المجموعة الفرعية لا تتبع هذا النادي'}), 400

    is_academy_player = subgroup is not None and subgroup.subgroup_type == 'academy'
    monthly_amount = _resolve_monthly_amount(subgroup, club)
    is_monthly_player = monthly_amount > 0
    subscription_start = data.get('subscriptionStartDate')
    subscription_end = data.get('subscriptionEndDate')

    if is_academy_player and not is_monthly_player:
        return jsonify({'error': 'المبلغ الشهري مطلوب للاعبي الأكاديمية'}), 400

    if is_monthly_player:
        if monthly_amount is None or monthly_amount <= 0:
            return jsonify({'error': 'المبلغ الشهري مطلوب للاعبي الأكاديمية'}), 400

    try:
        subscription_start_date = datetime.fromisoformat(subscription_start).date() if (is_monthly_player and subscription_start) else None
        subscription_end_date = datetime.fromisoformat(subscription_end).date() if (is_monthly_player and subscription_end) else None

        if is_monthly_player and subscription_start_date is None:
            subscription_start_date = date.today()
        if is_monthly_player and subscription_end_date is None and subscription_start_date is not None:
            subscription_end_date = _add_one_month_keep_day(subscription_start_date, subscription_start_date.day)

        if is_monthly_player and subscription_start_date and subscription_end_date and subscription_end_date <= subscription_start_date:
            return jsonify({'error': 'نهاية الاشتراك يجب أن تكون بعد البداية'}), 400

        renewal_day = None
        next_renewal_date = None
        raw_amount_due = data.get('amountDue')
        amount_due = float(raw_amount_due) if raw_amount_due is not None else None
        payment_status = data.get('paymentStatus', 'unpaid')
        if is_monthly_player:
            # Preserve extra due entered by user and add monthly subscription component.
            additional_due = float(amount_due or 0.0)
            if additional_due < 0:
                additional_due = 0.0
            amount_due = float(monthly_amount) + additional_due
            payment_status = 'unpaid'

        player = Player(
            full_name=data['fullName'],
            date_of_birth=datetime.fromisoformat(data['dateOfBirth']).date() if data.get('dateOfBirth') else None,
            payment_status=payment_status,
            amount_due=amount_due,
            monthly_amount=monthly_amount if is_monthly_player else None,
            renewal_day=renewal_day,
            next_renewal_date=next_renewal_date,
            subscription_start_date=subscription_start_date,
            subscription_end_date=subscription_end_date,
            notes=data.get('notes'),
            phone_number=data.get('phoneNumber'),
            image_url=data.get('imageUrl'),
            club_id=club_id,
            subgroup_id=subgroup_id,
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
    
    data = request.get_json() or {}
    
    subgroup_id_for_update = data.get('subgroupId', player.subgroup_id)
    subgroup_for_update = None
    if subgroup_id_for_update:
        subgroup_for_update = Subgroup.query.get(subgroup_id_for_update)
        if not subgroup_for_update:
            return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404

    is_academy_player = subgroup_for_update is not None and subgroup_for_update.subgroup_type == 'academy'
    club_id_for_update = data.get('clubId', player.club_id)
    club_for_update = Club.query.get(club_id_for_update) if club_id_for_update else None
    resolved_monthly = _resolve_monthly_amount(subgroup_for_update, club_for_update, player.monthly_amount)
    is_monthly_player = resolved_monthly > 0
    subscription_start = data.get('subscriptionStartDate')
    subscription_end = data.get('subscriptionEndDate')
    
    if 'fullName' in data:
        player.full_name = data['fullName']
    if 'dateOfBirth' in data:
        player.date_of_birth = datetime.fromisoformat(data['dateOfBirth']).date() if data['dateOfBirth'] else None
    if 'paymentStatus' in data:
        player.payment_status = data['paymentStatus']
    if 'amountDue' in data:
        if is_monthly_player:
            additional_due = float(data['amountDue'] or 0.0)
            if additional_due < 0:
                additional_due = 0.0
            player.amount_due = float(resolved_monthly or 0.0) + additional_due
        else:
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

    username_payload_present = 'username' in data
    password_payload_present = 'password' in data
    username = (data.get('username') or '').strip() if username_payload_present else None
    password = data.get('password') if password_payload_present else None
    user_account = User.query.filter_by(player_id=player.id).first()

    if username_payload_present:
        if username == '':
            if user_account:
                if password_payload_present and password:
                    return jsonify({'error': 'لا يمكن إرسال كلمة مرور بدون اسم مستخدم'}), 400
                db.session.delete(user_account)
                user_account = None
        else:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user and (not user_account or existing_user.id != user_account.id):
                return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400

            if user_account:
                user_account.username = username
                if password_payload_present and password:
                    if len(password) < 4:
                        return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
                    user_account.set_password(password)
            else:
                if not password:
                    return jsonify({'error': 'كلمة المرور مطلوبة عند إنشاء حساب جديد'}), 400
                if len(password) < 4:
                    return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
                user_account = User(
                    username=username,
                    role='player',
                    club_id=player.club_id,
                    player_id=player.id,
                )
                user_account.set_password(password)
                db.session.add(user_account)
    elif password_payload_present and password:
        if not user_account:
            return jsonify({'error': 'لا يوجد حساب مرتبط بهذا اللاعب. أدخل اسم المستخدم أولاً'}), 400
        if len(password) < 4:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
        user_account.set_password(password)

    if user_account:
        user_account.club_id = player.club_id

    if is_academy_player and not is_monthly_player:
        return jsonify({'error': 'المبلغ الشهري مطلوب للاعبي الأكاديمية'}), 400

    if is_monthly_player:
        player.monthly_amount = resolved_monthly

        if subscription_start is not None:
            player.subscription_start_date = datetime.fromisoformat(subscription_start).date() if subscription_start else None
        if subscription_end is not None:
            player.subscription_end_date = datetime.fromisoformat(subscription_end).date() if subscription_end else None

        # Backfill legacy monthly players created before subscription dates were introduced.
        if player.subscription_start_date is None:
            base_start = player.created_at.date() if player.created_at else date.today()
            player.subscription_start_date = base_start
        if player.subscription_end_date is None and player.subscription_start_date is not None:
            player.subscription_end_date = _add_one_month_keep_day(
                player.subscription_start_date,
                player.subscription_start_date.day,
            )

        if player.subscription_start_date is None or player.subscription_end_date is None:
            return jsonify({'error': 'تاريخ بداية ونهاية الاشتراك مطلوبان للاعب الاشتراك الشهري'}), 400
        if player.subscription_end_date <= player.subscription_start_date:
            return jsonify({'error': 'نهاية الاشتراك يجب أن تكون بعد البداية'}), 400

        # Monthly players payment status must follow due amount and revenues.
        if player.amount_due is None:
            player.amount_due = float(player.monthly_amount or 0.0)
        player.payment_status = 'paid' if float(player.amount_due or 0.0) <= 0 else 'unpaid'

        player.renewal_day = None
        player.next_renewal_date = None
    else:
        player.renewal_day = None
        player.next_renewal_date = None
        player.monthly_amount = None
        player.subscription_start_date = None
        player.subscription_end_date = None
    
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

    changed = False
    for p in players:
        if _apply_player_renewals(p):
            changed = True
    if changed:
        db.session.commit()

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
