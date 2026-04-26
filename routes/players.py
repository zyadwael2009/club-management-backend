from flask import Blueprint, request, jsonify, session
from models import db, Player, User, Coach, Subgroup, Club, PlayerPayment
from routes.auth import login_required, admin_or_superadmin_required
from branch_scope import effective_branch_id_for_user, resolve_creation_branch_for_user
from season_context import get_effective_season_id
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


def _resolve_monthly_amount(subgroup, club, current_player_monthly=None, requested_monthly=None):
    if requested_monthly is not None:
        return max(0.0, float(requested_monthly))

    if current_player_monthly is not None:
        current_monthly = float(current_player_monthly or 0.0)
        if current_monthly <= 0:
            return 0.0
        return current_monthly

    subgroup_monthly = float(subgroup.monthly_amount or 0.0) if subgroup else 0.0
    club_monthly = float(club.monthly_amount or 0.0) if club else 0.0
    if subgroup_monthly > 0:
        return subgroup_monthly
    if club_monthly > 0:
        return club_monthly
    return 0.0


def _resolve_league_due(subgroup, current_player_league=None, requested_league=None, legacy_amount_due=None):
    if requested_league is not None:
        return max(0.0, float(requested_league))

    if legacy_amount_due is not None:
        return max(0.0, float(legacy_amount_due))

    if current_player_league is not None:
        return max(0.0, float(current_player_league or 0.0))

    subgroup_league = float(subgroup.league_amount or 0.0) if subgroup else 0.0
    if subgroup_league > 0:
        return subgroup_league
    return 0.0


def _parse_optional_monthly_amount(raw_value):
    if raw_value is None or raw_value == '':
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError('المبلغ الشهري غير صالح')

    if value < 0:
        raise ValueError('المبلغ الشهري لا يمكن أن يكون أقل من صفر')

    return value


def _parse_optional_league_due(raw_value):
    if raw_value is None or raw_value == '':
        return None

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise ValueError('مبلغ اشتراك الدوري غير صالح')

    if value < 0:
        raise ValueError('مبلغ اشتراك الدوري لا يمكن أن يكون أقل من صفر')

    return value


def _apply_player_renewals(player, today=None):
    if not bool(player.is_active):
        if player.payment_status != 'inactive':
            player.payment_status = 'inactive'
            return True
        return False
    current_date = today or date.today()
    subgroup = player.subgroup
    club = player.club
    changed = False

    stored_monthly = player.monthly_amount
    resolved_monthly = float(stored_monthly or 0.0)
    stored_league_due = player.league_due
    resolved_league_due = float(stored_league_due or 0.0)

    # Backfill legacy rows that relied on subgroup/club defaults and had null monthly value.
    if stored_monthly is None:
        derived_monthly = _resolve_monthly_amount(subgroup, club)
        if derived_monthly > 0:
            resolved_monthly = derived_monthly
            player.monthly_amount = derived_monthly
            changed = True

    if stored_league_due is None:
        if resolved_monthly > 0:
            total_due = float(player.amount_due or 0.0)
            resolved_league_due = max(0.0, total_due - resolved_monthly)
        else:
            resolved_league_due = max(0.0, float(player.amount_due or 0.0))
        if player.amount_due is not None or resolved_league_due > 0:
            player.league_due = resolved_league_due
            changed = True

    if player.amount_due is not None and float(player.league_due or 0.0) > float(player.amount_due or 0.0):
        player.league_due = max(0.0, float(player.amount_due or 0.0))
        resolved_league_due = float(player.league_due or 0.0)
        changed = True

    if resolved_monthly <= 0:
        if player.amount_due is not None:
            normalized = max(0.0, float(player.amount_due or 0.0))
            if float(player.league_due or 0.0) != normalized:
                player.league_due = normalized
                changed = True
        return changed

    # Monthly subscription status is determined by payments of the current month.
    season_id = get_effective_season_id(default_to_current=True)
    month_start = date(current_date.year, current_date.month, 1)
    month_end = _add_one_month_keep_day(month_start, 1)
    monthly_query = PlayerPayment.query.filter_by(
        player_id=player.id,
        payment_type='monthly_subscription',
    ).filter(
        PlayerPayment.payment_date >= month_start,
        PlayerPayment.payment_date < month_end,
    )
    if season_id:
        monthly_query = monthly_query.filter_by(season_id=season_id)
    has_current_month_payment = monthly_query.first() is not None

    if not player.subscription_end_date:
        base_start = player.subscription_start_date or (player.created_at.date() if player.created_at else current_date)
        player.subscription_start_date = base_start
        player.subscription_end_date = _add_one_month_keep_day(base_start, base_start.day)
        changed = True
    monthly_due_component = 0.0 if has_current_month_payment else float(resolved_monthly)
    expected_total_due = monthly_due_component + float(resolved_league_due)
    if float(player.amount_due or 0.0) != expected_total_due:
        player.amount_due = expected_total_due
        changed = True
    expected_status = 'paid' if expected_total_due <= 0 else 'unpaid'
    if player.payment_status != expected_status:
        player.payment_status = expected_status
        changed = True

    return changed


def _set_player_active_state(player, make_active):
    player.is_active = bool(make_active)
    player.updated_at = datetime.utcnow()

    if not make_active:
        if player.paused_amount_due is None:
            player.paused_amount_due = max(0.0, float(player.amount_due or 0.0))
        if player.paused_league_due is None:
            player.paused_league_due = max(0.0, float(player.league_due or 0.0))
        player.paused_at = datetime.utcnow()
        player.amount_due = 0.0
        player.league_due = 0.0
        player.payment_status = 'inactive'
        return

    restored_amount_due = max(0.0, float(player.paused_amount_due or 0.0))
    restored_league_due = max(0.0, float(player.paused_league_due or 0.0))
    if restored_league_due > restored_amount_due:
        restored_league_due = restored_amount_due

    player.amount_due = restored_amount_due
    player.league_due = restored_league_due
    player.payment_status = 'paid' if restored_amount_due <= 0 else 'unpaid'
    player.paused_amount_due = None
    player.paused_league_due = None
    player.paused_at = None


@players_bp.route('', methods=['GET'])
@login_required
def get_players():
    """Get all players (filtered by club for admin, all for superadmin)"""
    current_user = User.query.get(session['user_id'])
    
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    
    query = Player.query
    branch_id = effective_branch_id_for_user(current_user)
    
    # Role-based filtering
    if current_user.role == 'admin':
        # Admin sees only their club's players
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
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
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    
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
    elif current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
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
    elif current_user.role == 'branch_manager':
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
        .filter(Player.is_active == True)
        .filter(Player.subscription_end_date == today)
        .order_by(Player.full_name.asc())
        .all()
    )
    if current_user.role == 'branch_manager':
        rows = [(player, subgroup) for player, subgroup in rows if player.branch_id == current_user.branch_id]

    payload = []
    total = 0.0
    for player, subgroup in rows:
        total += float(player.monthly_amount or 0.0)
        payload.append({
            'id': player.id,
            'fullName': player.full_name,
            'monthlyAmount': float(player.monthly_amount or 0.0),
            'leagueDue': float(player.league_due or 0.0),
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


@players_bp.route('/<player_id>/toggle-active', methods=['PUT'])
@admin_or_superadmin_required
def toggle_player_active(player_id):
    player = Player.query.get_or_404(player_id)
    current_user = User.query.get(session['user_id'])

    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا اللاعب'}), 403
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا اللاعب'}), 403

    data = request.get_json() or {}
    make_active = data.get('isActive')
    if make_active is None:
        make_active = not bool(player.is_active)

    _set_player_active_state(player, bool(make_active))
    db.session.commit()
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
    if current_user.role == 'branch_manager' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة لاعبين لهذا النادي'}), 403
    branch_id, branch_error = resolve_creation_branch_for_user(current_user, club_id)
    if branch_error:
        return jsonify({'error': branch_error}), 400
    
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
        if branch_id and subgroup.branch_id != branch_id:
            return jsonify({'error': 'المجموعة الفرعية لا تتبع الفرع المحدد'}), 400

    try:
        requested_monthly = _parse_optional_monthly_amount(data.get('monthlyAmount'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        requested_league_due = _parse_optional_league_due(data.get('leagueDue'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    monthly_amount = _resolve_monthly_amount(
        subgroup,
        club,
        requested_monthly=requested_monthly,
    )
    is_monthly_player = monthly_amount > 0
    subscription_start = data.get('subscriptionStartDate')
    subscription_end = data.get('subscriptionEndDate')

    stored_monthly_amount = (
        requested_monthly
        if requested_monthly is not None
        else (monthly_amount if is_monthly_player else None)
    )

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
        legacy_amount_due = float(raw_amount_due) if raw_amount_due is not None else None
        if legacy_amount_due is not None and legacy_amount_due < 0:
            legacy_amount_due = 0.0
        league_due = _resolve_league_due(
            subgroup,
            requested_league=requested_league_due,
            legacy_amount_due=legacy_amount_due,
        )

        amount_due = None
        payment_status = data.get('paymentStatus', 'unpaid')
        if is_monthly_player:
            amount_due = float(monthly_amount) + float(league_due)
            payment_status = 'unpaid'
        else:
            amount_due = float(league_due)
            payment_status = 'paid' if amount_due <= 0 else 'unpaid'

        player = Player(
            full_name=data['fullName'],
            date_of_birth=datetime.fromisoformat(data['dateOfBirth']).date() if data.get('dateOfBirth') else None,
            payment_status=payment_status,
            amount_due=amount_due,
            monthly_amount=stored_monthly_amount,
            league_due=league_due,
            renewal_day=renewal_day,
            next_renewal_date=next_renewal_date,
            subscription_start_date=subscription_start_date,
            subscription_end_date=subscription_end_date,
            notes=data.get('notes'),
            phone_number=data.get('phoneNumber'),
            image_url=data.get('imageUrl'),
            club_id=club_id,
            branch_id=branch_id,
            subgroup_id=subgroup_id,
            pin=data.get('pin'),
            is_active=bool(data.get('isActive', True)),
        )
        if not player.is_active:
            _set_player_active_state(player, False)
        
        db.session.add(player)
        db.session.flush()  # Get the player ID
        
        # Create user if username provided
        if username:
            user = User(
                username=username,
                role='player',
                club_id=club_id,
                branch_id=branch_id,
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
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا اللاعب'}), 403
    
    data = request.get_json() or {}
    
    subgroup_id_for_update = data.get('subgroupId', player.subgroup_id)
    subgroup_for_update = None
    if subgroup_id_for_update:
        subgroup_for_update = Subgroup.query.get(subgroup_id_for_update)
        if not subgroup_for_update:
            return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404

    club_id_for_update = data.get('clubId', player.club_id)
    club_for_update = Club.query.get(club_id_for_update) if club_id_for_update else None

    try:
        requested_monthly = _parse_optional_monthly_amount(data.get('monthlyAmount'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    try:
        requested_league_due = _parse_optional_league_due(data.get('leagueDue'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    resolved_monthly = _resolve_monthly_amount(
        subgroup_for_update,
        club_for_update,
        player.monthly_amount,
        requested_monthly,
    )
    existing_total_due = max(0.0, float(player.amount_due or 0.0))
    existing_league_due = max(0.0, float(player.league_due or 0.0))
    if existing_league_due > existing_total_due:
        existing_league_due = existing_total_due
    existing_monthly_outstanding_due = max(0.0, existing_total_due - existing_league_due)

    is_monthly_player = resolved_monthly > 0
    subscription_start = data.get('subscriptionStartDate')
    subscription_end = data.get('subscriptionEndDate')
    
    if 'fullName' in data:
        player.full_name = data['fullName']
    if 'dateOfBirth' in data:
        player.date_of_birth = datetime.fromisoformat(data['dateOfBirth']).date() if data['dateOfBirth'] else None
    if 'paymentStatus' in data:
        player.payment_status = data['paymentStatus']

    due_override = None
    if 'amountDue' in data:
        try:
            due_override = float(data['amountDue'] or 0.0)
        except (TypeError, ValueError):
            return jsonify({'error': 'المبلغ المستحق غير صالح'}), 400
        if due_override < 0:
            due_override = 0.0

    league_due_override = None
    if requested_league_due is not None:
        league_due_override = requested_league_due
    elif due_override is not None:
        # Backward compatibility: amountDue for monthly players represented extra due.
        league_due_override = due_override

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
    if 'isActive' in data:
        _set_player_active_state(player, bool(data['isActive']))

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
        user_account.branch_id = player.branch_id

    if is_monthly_player:
        player.monthly_amount = resolved_monthly

        if league_due_override is not None:
            player.league_due = max(0.0, float(league_due_override))
            if due_override is not None:
                requested_total_due = max(0.0, float(due_override))
                if requested_total_due < float(player.league_due or 0.0):
                    requested_total_due = float(player.league_due or 0.0)
                player.amount_due = requested_total_due
            else:
                player.amount_due = existing_monthly_outstanding_due + float(player.league_due or 0.0)
        else:
            if player.league_due is None:
                inferred_league_due = max(
                    0.0,
                    float(player.amount_due or 0.0) - float(resolved_monthly or 0.0),
                )
                player.league_due = inferred_league_due

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
            player.amount_due = float(player.monthly_amount or 0.0) + float(player.league_due or 0.0)
        player.payment_status = 'paid' if float(player.amount_due or 0.0) <= 0 else 'unpaid'

        player.renewal_day = None
        player.next_renewal_date = None
    else:
        player.renewal_day = None
        player.next_renewal_date = None
        if requested_monthly is not None and requested_monthly <= 0:
            player.monthly_amount = 0.0
        elif player.monthly_amount is not None and float(player.monthly_amount or 0.0) == 0.0:
            player.monthly_amount = 0.0
        else:
            player.monthly_amount = None

        if league_due_override is not None:
            player.league_due = max(0.0, float(league_due_override))
            player.amount_due = float(player.league_due or 0.0)
        elif player.amount_due is not None:
            player.league_due = max(0.0, float(player.amount_due or 0.0))
        elif player.league_due is None:
            player.league_due = 0.0

        player.subscription_start_date = None
        player.subscription_end_date = None

        if player.amount_due is not None:
            player.payment_status = 'paid' if float(player.amount_due or 0.0) <= 0 else 'unpaid'
    
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
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
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
    branch_id = effective_branch_id_for_user(current_user)
    
    # Role-based filtering
    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
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
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    
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
