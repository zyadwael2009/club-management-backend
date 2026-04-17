from flask import Blueprint, request, jsonify, session
from models import db, Training, Subgroup, User, Player, CheckIn, CheckInTraining, TrainingSubgroup
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime, timezone
from sqlalchemy import or_
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

trainings_bp = Blueprint('trainings', __name__)

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


def _to_egypt_text(dt):
    if not dt:
        return None
    aware = dt.replace(tzinfo=_UTC) if dt.tzinfo is None else dt.astimezone(_UTC)
    return aware.astimezone(_EGYPT).strftime('%H:%M:%S')


def _resolve_scope_from_subgroups(subgroups):
    if not subgroups:
        return 'club'

    subgroup_types = {(subgroup.subgroup_type or 'club').strip().lower() for subgroup in subgroups}
    if subgroup_types == {'academy'}:
        return 'academy'

    if subgroup_types == {'club'}:
        if all((subgroup.birth_year or 0) == 0 for subgroup in subgroups):
            return 'first_team'
        return 'club'

    return 'club'


def _ordered_subgroups(subgroup_ids):
    if not subgroup_ids:
        return []

    rows = Subgroup.query.filter(Subgroup.id.in_(subgroup_ids)).all()
    subgroup_map = {row.id: row for row in rows}
    return [subgroup_map[subgroup_id] for subgroup_id in subgroup_ids if subgroup_id in subgroup_map]


@trainings_bp.route('', methods=['GET'])
@login_required
def list_trainings():
    """List trainings (role-based filtering)"""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')

    query = Training.query

    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role != 'superadmin':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif club_id:
        query = query.filter_by(club_id=club_id)

    if subgroup_id:
        query = query.outerjoin(
            TrainingSubgroup,
            TrainingSubgroup.training_id == Training.id,
        ).filter(
            or_(Training.subgroup_id == subgroup_id, TrainingSubgroup.subgroup_id == subgroup_id)
        ).distinct()

    trainings = query.order_by(Training.training_date.desc(), Training.created_at.desc()).all()
    return jsonify([t.to_dict() for t in trainings]), 200


@trainings_bp.route('', methods=['POST'])
@admin_or_superadmin_required
def create_training():
    """Create a training session assigned to one or more subgroups"""
    current_user = User.query.get(session['user_id'])
    data = request.get_json() or {}

    name = (data.get('name') or '').strip()
    club_id = data.get('clubId')
    subgroup_ids = data.get('subgroupIds')
    if subgroup_ids is None:
        legacy_subgroup_id = data.get('subgroupId')
        subgroup_ids = [legacy_subgroup_id] if legacy_subgroup_id else []
    training_date = data.get('trainingDate')
    start_time = (data.get('startTime') or '').strip()

    if not club_id:
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    if not training_date:
        return jsonify({'error': 'تاريخ التدريب مطلوب'}), 400

    if not isinstance(subgroup_ids, list):
        return jsonify({'error': 'المجموعات الفرعية يجب أن تكون قائمة'}), 400

    normalized_ids = []
    seen_ids = set()
    for subgroup_id in subgroup_ids:
        subgroup_id_text = str(subgroup_id or '').strip()
        if not subgroup_id_text or subgroup_id_text in seen_ids:
            continue
        seen_ids.add(subgroup_id_text)
        normalized_ids.append(subgroup_id_text)

    if not normalized_ids:
        return jsonify({'error': 'يجب اختيار مجموعة فرعية واحدة على الأقل'}), 400

    if start_time and not re.match(r'^(?:[01]\d|2[0-3]):[0-5]\d$', start_time):
        return jsonify({'error': 'وقت بدء التدريب يجب أن يكون بصيغة HH:MM'}), 400

    ordered_subgroups = _ordered_subgroups(normalized_ids)
    if len(ordered_subgroups) != len(normalized_ids):
        return jsonify({'error': 'إحدى المجموعات الفرعية غير موجودة'}), 404

    if any(subgroup.club_id != club_id for subgroup in ordered_subgroups):
        return jsonify({'error': 'إحدى المجموعات الفرعية لا تتبع هذا النادي'}), 400

    if current_user.role == 'admin' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة تدريب لهذا النادي'}), 403

    training_scope = _resolve_scope_from_subgroups(ordered_subgroups)
    subgroup_names = [subgroup.name for subgroup in ordered_subgroups]
    if not name:
        if len(subgroup_names) == 1:
            name = f'تدريب {subgroup_names[0]}'
        elif len(subgroup_names) == 2:
            name = f'تدريب {subgroup_names[0]} + {subgroup_names[1]}'
        else:
            name = f'تدريب {subgroup_names[0]} + {len(subgroup_names) - 1} مجموعات'

    try:
        parsed_training_date = datetime.fromisoformat(training_date).date()
    except ValueError:
        return jsonify({'error': 'صيغة تاريخ التدريب غير صحيحة'}), 400

    try:
        training = Training(
            name=name,
            club_id=club_id,
            subgroup_id=normalized_ids[0],
            training_scope=training_scope,
            training_date=parsed_training_date,
            start_time=start_time or None,
            notes=data.get('notes'),
        )
        db.session.add(training)

        db.session.flush()

        for subgroup_id in normalized_ids:
            db.session.add(TrainingSubgroup(
                training_id=training.id,
                subgroup_id=subgroup_id,
            ))

        db.session.commit()
        return jsonify(training.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء التدريب: {str(e)}'}), 500


@trainings_bp.route('/<training_id>/attendance', methods=['GET'])
@login_required
def get_training_attendance(training_id):
    """Get all players assigned to this training scope with attended status."""
    training = Training.query.get(training_id)
    if not training:
        return jsonify({'error': 'التدريب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and training.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and training.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role not in ['admin', 'coach', 'superadmin']:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    subgroup_ids = training.assigned_subgroup_ids()

    if not subgroup_ids:
        scope = training.training_scope or 'club'
        if scope == 'first_team':
            subgroups = Subgroup.query.filter_by(
                club_id=training.club_id,
                subgroup_type='club',
                birth_year=0,
            ).all()
        else:
            subgroups = Subgroup.query.filter_by(
                club_id=training.club_id,
                subgroup_type=scope,
            ).filter(Subgroup.birth_year != 0).all()
        subgroup_ids = [s.id for s in subgroups]

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
    ).order_by(CheckIn.timestamp.desc()).all()

    latest_checkin_by_player = {}
    for player_id, timestamp in attended_rows:
        if player_id not in latest_checkin_by_player:
            latest_checkin_by_player[player_id] = timestamp

    result_players = []
    for player in players:
        result_players.append({
            'id': player.id,
            'fullName': player.full_name,
            'subgroupId': player.subgroup_id,
            'attended': player.id in latest_checkin_by_player,
            'checkedInAt': _to_egypt_iso(latest_checkin_by_player[player.id]) if player.id in latest_checkin_by_player else None,
            'checkedInAtText': _to_egypt_text(latest_checkin_by_player[player.id]) if player.id in latest_checkin_by_player else None,
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

    try:
        CheckInTraining.query.filter_by(training_id=training.id).delete(synchronize_session=False)
        TrainingSubgroup.query.filter_by(training_id=training.id).delete(synchronize_session=False)
        db.session.delete(training)
        db.session.commit()
        return jsonify({'message': 'تم حذف التدريب بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف التدريب: {str(e)}'}), 500
