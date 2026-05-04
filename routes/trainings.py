from flask import Blueprint, request, jsonify, session
from models import db, Training, Subgroup, User, Player, CheckIn, CheckInTraining, TrainingSubgroup
from routes.auth import login_required, admin_or_superadmin_required, ensure_coach_permission
from branch_scope import effective_branch_id_for_user, resolve_creation_branch_for_user
from season_context import get_effective_season_id
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import or_
import re

trainings_bp = Blueprint('trainings', __name__)


def _safe_zoneinfo(key, fallback):
    try:
        return ZoneInfo(key)
    except ZoneInfoNotFoundError:
        return fallback


_UTC = _safe_zoneinfo('UTC', timezone.utc)
_EGYPT = _safe_zoneinfo('Africa/Cairo', timezone.utc)
_TIME_RE = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)$')


def _to_egypt_iso(dt):
    if not dt:
        return None
    aware = dt.replace(tzinfo=_UTC) if dt.tzinfo is None else dt.astimezone(_UTC)
    return aware.astimezone(_EGYPT).isoformat()


def _to_egypt_text(dt):
    if not dt:
        return None
    aware = dt.replace(tzinfo=_UTC) if dt.tzinfo is None else dt.astimezone(_UTC)
    return aware.astimezone(_EGYPT).strftime('%H:%M:%S')


def _resolve_scope_from_subgroups(subgroups):
    if not subgroups:
        return 'club'

    if len(subgroups) == 1:
        subgroup = subgroups[0]
        if subgroup.subgroup_type == 'club' and (subgroup.birth_year or 0) == 0:
            return 'first_team'

    subgroup_types = {subgroup.subgroup_type for subgroup in subgroups}
    if len(subgroup_types) == 1:
        only_type = next(iter(subgroup_types))
        return 'academy' if only_type == 'academy' else 'club'

    return 'club'


@trainings_bp.route('', methods=['GET'])
@login_required
def list_trainings():
    """List trainings (role-based filtering)"""
    current_user = User.query.get(session['user_id'])

    permission_error = ensure_coach_permission(current_user, 'trainings')
    if permission_error:
        return permission_error
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    season_id = get_effective_season_id(default_to_current=True)

    query = Training.query
    branch_id = effective_branch_id_for_user(current_user)

    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'player':
        if not current_user.player_id:
            return jsonify([]), 200

        player = Player.query.get(current_user.player_id)
        if not player or not player.club_id or not player.subgroup_id:
            return jsonify([]), 200

        query = query.filter_by(club_id=player.club_id)
        subgroup_id = player.subgroup_id
    elif current_user.role != 'superadmin':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif club_id:
        query = query.filter_by(club_id=club_id)
    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    if season_id:
        query = query.filter_by(season_id=season_id)

    if subgroup_id:
        query = query.outerjoin(
            TrainingSubgroup,
            TrainingSubgroup.training_id == Training.id,
        ).filter(
            or_(
                Training.subgroup_id == subgroup_id,
                TrainingSubgroup.subgroup_id == subgroup_id,
            )
        ).distinct()

    trainings = query.order_by(Training.training_date.desc(), Training.created_at.desc()).all()
    return jsonify([training.to_dict() for training in trainings]), 200


@trainings_bp.route('', methods=['POST'])
@admin_or_superadmin_required
def create_training():
    """Create a training session assigned to one or more subgroups."""
    current_user = User.query.get(session['user_id'])
    data = request.get_json() or {}
    season_id = get_effective_season_id(default_to_current=True)

    club_id = data.get('clubId')
    subgroup_ids = data.get('subgroupIds')
    if (not subgroup_ids or not isinstance(subgroup_ids, list)) and data.get('subgroupId'):
        subgroup_ids = [data.get('subgroupId')]
    subgroup_ids = [subgroup_id for subgroup_id in (subgroup_ids or []) if subgroup_id]

    training_date = data.get('trainingDate')
    start_time = (data.get('startTime') or '').strip() or None
    notes = data.get('notes')
    name = (data.get('name') or '').strip() or 'حصة تدريب'

    if not club_id:
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    if not training_date:
        return jsonify({'error': 'تاريخ التدريب مطلوب'}), 400
    if not subgroup_ids:
        return jsonify({'error': 'يجب اختيار مجموعة فرعية واحدة على الأقل'}), 400
    if start_time and not _TIME_RE.match(start_time):
        return jsonify({'error': 'صيغة الوقت غير صحيحة. استخدم HH:MM'}), 400

    if current_user.role == 'admin' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة تدريب لهذا النادي'}), 403
    if current_user.role == 'branch_manager' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة تدريب لهذا النادي'}), 403
    branch_id, branch_error = resolve_creation_branch_for_user(current_user, club_id)
    if branch_error:
        return jsonify({'error': branch_error}), 400

    unique_subgroup_ids = list(dict.fromkeys(subgroup_ids))
    subgroups = Subgroup.query.filter(Subgroup.id.in_(unique_subgroup_ids)).all()
    if len(subgroups) != len(unique_subgroup_ids):
        return jsonify({'error': 'إحدى المجموعات الفرعية غير موجودة'}), 404

    for subgroup in subgroups:
        if subgroup.club_id != club_id:
            return jsonify({'error': 'إحدى المجموعات الفرعية لا تتبع هذا النادي'}), 400
        if branch_id and subgroup.branch_id != branch_id:
            return jsonify({'error': 'إحدى المجموعات الفرعية لا تتبع الفرع المحدد'}), 400

    try:
        parsed_date = datetime.fromisoformat(training_date).date()
    except ValueError:
        return jsonify({'error': 'صيغة تاريخ التدريب غير صحيحة'}), 400

    training_scope = _resolve_scope_from_subgroups(subgroups)
    primary_subgroup_id = unique_subgroup_ids[0]

    try:
        training = Training(
            name=name,
            club_id=club_id,
            branch_id=branch_id,
            subgroup_id=primary_subgroup_id,
            season_id=season_id,
            training_scope=training_scope,
            training_date=parsed_date,
            start_time=start_time,
            notes=notes,
        )
        db.session.add(training)
        db.session.flush()

        for subgroup_id in unique_subgroup_ids:
            db.session.add(TrainingSubgroup(training_id=training.id, subgroup_id=subgroup_id))

        db.session.commit()
        return jsonify(training.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء التدريب: {str(e)}'}), 500


@trainings_bp.route('/<training_id>/attendance', methods=['GET'])
@login_required
def get_training_attendance(training_id):
    """Get all players assigned to this training with attended status."""
    training = Training.query.get(training_id)
    if not training:
        return jsonify({'error': 'التدريب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'trainings')
    if permission_error:
        return permission_error
    if current_user.role == 'admin' and training.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and training.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and training.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role not in ['admin', 'coach', 'superadmin', 'branch_manager']:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    subgroup_ids = training.assigned_subgroup_ids()
    if subgroup_ids:
        players = Player.query.filter(
            Player.club_id == training.club_id,
            Player.subgroup_id.in_(subgroup_ids),
        ).order_by(Player.full_name.asc()).all()
    else:
        players = []

    attended_rows = db.session.query(CheckIn.player_id, CheckIn.timestamp).join(
        CheckInTraining,
        CheckInTraining.checkin_id == CheckIn.id,
    ).filter(
        CheckInTraining.training_id == training.id,
        CheckIn.season_id == training.season_id if training.season_id else True,
    ).order_by(CheckIn.timestamp.desc()).all()

    latest_checkin_by_player = {}
    for player_id, timestamp in attended_rows:
        if player_id not in latest_checkin_by_player:
            latest_checkin_by_player[player_id] = timestamp

    result_players = []
    for player in players:
        checked_in_at = latest_checkin_by_player.get(player.id)
        result_players.append({
            'id': player.id,
            'fullName': player.full_name,
            'subgroupId': player.subgroup_id,
            'attended': checked_in_at is not None,
            'checkedInAt': _to_egypt_iso(checked_in_at) if checked_in_at else None,
            'checkedInAtText': _to_egypt_text(checked_in_at) if checked_in_at else None,
        })

    return jsonify({
        'training': training.to_dict(),
        'players': result_players,
    }), 200


@trainings_bp.route('/<training_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_training(training_id):
    training = Training.query.get(training_id)
    if not training:
        return jsonify({'error': 'التدريب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and training.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا التدريب'}), 403
    if current_user.role == 'branch_manager' and training.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا التدريب'}), 403

    try:
        TrainingSubgroup.query.filter_by(training_id=training.id).delete(synchronize_session=False)
        db.session.delete(training)
        db.session.commit()
        return jsonify({'message': 'تم حذف التدريب بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف التدريب: {str(e)}'}), 500
