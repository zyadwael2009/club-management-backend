from flask import Blueprint, request, jsonify, session
from models import db, CheckIn, Player, User, Training, CheckInTraining, TrainingSubgroup
from routes.auth import login_required, ensure_coach_permission
from branch_scope import effective_branch_id_for_user
from season_context import get_effective_season_id
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

checkins_bp = Blueprint('checkins', __name__)

def _safe_zoneinfo(key, fallback):
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError:
        return fallback


_UTC = _safe_zoneinfo('UTC', timezone.utc)
_EGYPT = _safe_zoneinfo('Africa/Cairo', timezone.utc)


def _to_egypt_iso(dt):
    if not dt:
        return None
    aware = dt.replace(tzinfo=_UTC) if dt.tzinfo is None else dt.astimezone(_UTC)
    return aware.astimezone(_EGYPT).isoformat()


def _append_training_info(checkins):
    checkin_ids = [c.id for c in checkins]
    if not checkin_ids:
        return [c.to_dict() for c in checkins]

    links = CheckInTraining.query.filter(CheckInTraining.checkin_id.in_(checkin_ids)).all()
    training_ids = [l.training_id for l in links]
    trainings = Training.query.filter(Training.id.in_(training_ids)).all() if training_ids else []

    training_by_id = {t.id: t for t in trainings}
    training_by_checkin = {l.checkin_id: training_by_id.get(l.training_id) for l in links}

    payload = []
    for checkin in checkins:
        row = checkin.to_dict()
        row['timestamp'] = _to_egypt_iso(checkin.timestamp)
        training = training_by_checkin.get(checkin.id)
        if training is not None:
            row['trainingId'] = training.id
            row['trainingName'] = training.name
        payload.append(row)
    return payload


def _is_player_allowed_for_training(player, training):
    """Validate player subgroup against training scope."""
    if player.subgroup_id is None:
        return False

    assigned_subgroup_ids = [
        row.subgroup_id
        for row in TrainingSubgroup.query.filter_by(training_id=training.id).all()
        if row.subgroup_id
    ]
    if training.subgroup_id and training.subgroup_id not in assigned_subgroup_ids:
        assigned_subgroup_ids.append(training.subgroup_id)

    if assigned_subgroup_ids:
        return player.subgroup_id in assigned_subgroup_ids

    if training.subgroup_id == player.subgroup_id:
        return True

    scope = (training.training_scope or 'club').strip().lower()
    subgroup = player.subgroup
    if subgroup is None:
        return False

    if scope == 'academy':
        return subgroup.subgroup_type == 'academy' and subgroup.birth_year != 0
    if scope == 'club':
        return subgroup.subgroup_type == 'club' and subgroup.birth_year != 0
    if scope == 'first_team':
        return subgroup.subgroup_type == 'club' and subgroup.birth_year == 0
    return False


@checkins_bp.route('', methods=['GET'])
@login_required
def get_checkins():
    """Get all check-ins (filtered by club for admin/coach)"""
    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_history')
    if permission_error:
        return permission_error

    permission_error = ensure_coach_permission(current_user, 'checkin_history')
    if permission_error:
        return permission_error
    club_id = request.args.get('club_id')
    limit = request.args.get('limit', 50, type=int)
    season_id = get_effective_season_id(default_to_current=True)
    
    query = CheckIn.query
    branch_id = effective_branch_id_for_user(current_user)
    
    # Role-based filtering
    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'player':
        # Player sees only their check-ins
        query = query.filter_by(player_id=current_user.player_id)
    else:
        # Superadmin can filter by club
        if club_id:
            query = query.filter_by(club_id=club_id)
    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    if season_id:
        query = query.filter_by(season_id=season_id)
    
    checkins = query.order_by(CheckIn.timestamp.desc()).limit(limit).all()
    return jsonify(_append_training_info(checkins))


@checkins_bp.route('/player/<player_id>', methods=['GET'])
@login_required
def get_player_checkins(player_id):
    """Get check-ins for a specific player"""
    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_history')
    if permission_error:
        return permission_error
    permission_error = ensure_coach_permission(current_user, 'checkin_history')
    if permission_error:
        return permission_error
    player = Player.query.get(player_id)
    
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    # Check permissions
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player' and player.id != current_user.player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    limit = request.args.get('limit', 20, type=int)
    season_id = get_effective_season_id(default_to_current=True)
    
    checkins_query = CheckIn.query.filter_by(player_id=player_id)
    if season_id:
        checkins_query = checkins_query.filter_by(season_id=season_id)

    checkins = checkins_query\
        .order_by(CheckIn.timestamp.desc())\
        .limit(limit).all()

    return jsonify(_append_training_info(checkins))


@checkins_bp.route('', methods=['POST'])
@login_required
def create_checkin():
    """Create a new check-in"""
    data = request.get_json()
    season_id = get_effective_season_id(default_to_current=True)

    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_scanner')
    if permission_error:
        return permission_error
    
    if not data or not data.get('playerId'):
        return jsonify({'error': 'معرف اللاعب مطلوب'}), 400

    if not data.get('trainingId'):
        return jsonify({'error': 'يجب اختيار التدريب قبل تسجيل الحضور'}), 400
    
    # Get player to create snapshot
    player = Player.query.get(data['playerId'])
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    if not bool(player.is_active):
        return jsonify({'error': 'لا يمكن تسجيل حضور لاعب غير نشط'}), 400
    
    current_user = current_user or User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_scanner')
    if permission_error:
        return permission_error
    
    # Check permissions (admin/coach can check-in any player in their club)
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا اللاعب'}), 403
    elif current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا اللاعب'}), 403
    elif current_user.role == 'coach' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا اللاعب'}), 403

    training = Training.query.get(data['trainingId'])
    if not training:
        return jsonify({'error': 'التدريب غير موجود'}), 404

    if season_id and training.season_id and training.season_id != season_id:
        return jsonify({'error': 'التدريب لا يتبع الموسم المحدد'}), 400

    if training.club_id != player.club_id:
        return jsonify({'error': 'التدريب لا يتبع نفس نادي اللاعب'}), 400

    subgroup = player.subgroup
    is_monthly_subscription = float(player.monthly_amount or 0.0) > 0
    if subgroup is not None and subgroup.subgroup_type == 'academy' and is_monthly_subscription:
        if player.subscription_end_date and player.subscription_end_date < date.today():
            player.payment_status = 'unpaid'
            monthly = float(player.monthly_amount or subgroup.monthly_amount or 0.0)
            if monthly > 0 and float(player.amount_due or 0.0) <= 0:
                player.amount_due = monthly
            db.session.commit()
            return jsonify({'error': 'انتهى اشتراك اللاعب. يرجى التجديد أولاً'}), 400

    if not _is_player_allowed_for_training(player, training):
        return jsonify({'error': 'اللاعب غير مسموح له بهذا التدريب حسب نوع المجموعة'}), 400

    existing_link = db.session.query(CheckInTraining.id).join(
        CheckIn,
        CheckIn.id == CheckInTraining.checkin_id,
    ).filter(
        CheckIn.player_id == player.id,
        CheckIn.season_id == season_id if season_id else True,
        CheckInTraining.training_id == training.id,
    ).first()
    if existing_link:
        return jsonify({'error': 'تم تسجيل حضور هذا اللاعب لهذا التدريب بالفعل'}), 409
    
    checkin = CheckIn(
        player_id=data['playerId'],
        club_id=data.get('clubId') or player.club_id,
        branch_id=player.branch_id,
        season_id=season_id,
        player_name=player.full_name,
        player_payment_status=player.payment_status,
    )

    db.session.add(checkin)
    db.session.flush()

    link = CheckInTraining(
        checkin_id=checkin.id,
        training_id=training.id,
    )
    db.session.add(link)
    db.session.commit()

    response = checkin.to_dict()
    response['timestamp'] = _to_egypt_iso(checkin.timestamp)
    response['trainingId'] = training.id
    response['trainingName'] = training.name
    return jsonify(response), 201


@checkins_bp.route('/<checkin_id>', methods=['DELETE'])
@login_required
def delete_checkin(checkin_id):
    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_history')
    if permission_error:
        return permission_error

    if current_user.role not in ['superadmin', 'admin', 'branch_manager', 'coach']:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    checkin = CheckIn.query.get(checkin_id)
    if not checkin:
        return jsonify({'error': 'تسجيل الحضور غير موجود'}), 404

    if current_user.role == 'admin' and checkin.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للحذف'}), 403
    if current_user.role == 'branch_manager' and checkin.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للحذف'}), 403
    if current_user.role == 'coach' and checkin.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للحذف'}), 403

    link = CheckInTraining.query.filter_by(checkin_id=checkin.id).first()
    if link:
        db.session.delete(link)
    db.session.delete(checkin)
    db.session.commit()
    return jsonify({'message': 'تم حذف تسجيل الحضور'}), 200
