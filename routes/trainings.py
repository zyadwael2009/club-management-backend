from flask import Blueprint, request, jsonify, session
from models import db, Training, Subgroup, User, Player, CheckIn, CheckInTraining
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime
from zoneinfo import ZoneInfo

trainings_bp = Blueprint('trainings', __name__)

_UTC = ZoneInfo('UTC')
_EGYPT = ZoneInfo('Africa/Cairo')


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
        query = query.filter_by(subgroup_id=subgroup_id)

    trainings = query.order_by(Training.training_date.desc(), Training.created_at.desc()).all()
    return jsonify([t.to_dict() for t in trainings]), 200


@trainings_bp.route('', methods=['POST'])
@admin_or_superadmin_required
def create_training():
    """Create a training session (subgroup optional)"""
    current_user = User.query.get(session['user_id'])
    data = request.get_json() or {}

    name = data.get('name')
    club_id = data.get('clubId')
    subgroup_id = data.get('subgroupId')
    training_scope = (data.get('trainingScope') or 'club').strip().lower()
    training_date = data.get('trainingDate')

    if not name:
        return jsonify({'error': 'اسم التدريب مطلوب'}), 400
    if not club_id:
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    if not training_date:
        return jsonify({'error': 'تاريخ التدريب مطلوب'}), 400
    if training_scope not in ['club', 'academy', 'first_team']:
        return jsonify({'error': 'نوع التدريب يجب أن يكون club أو academy أو first_team'}), 400

    if current_user.role == 'admin' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة تدريب لهذا النادي'}), 403

    if subgroup_id:
        subgroup = Subgroup.query.get(subgroup_id)
        if not subgroup:
            return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
        if subgroup.club_id != club_id:
            return jsonify({'error': 'المجموعة الفرعية لا تتبع هذا النادي'}), 400
        if training_scope == 'first_team':
            if subgroup.subgroup_type != 'club' or subgroup.birth_year != 0:
                return jsonify({'error': 'تدريب الفريق الأول يتطلب مجموعة الفريق الأول'}), 400
        elif subgroup.subgroup_type != training_scope:
            return jsonify({'error': 'نوع المجموعة لا يطابق نوع التدريب'}), 400
    else:
        # Keep DB compatibility where subgroup is required by selecting the first valid subgroup.
        if training_scope == 'first_team':
            fallback_subgroup = Subgroup.query.filter_by(
                club_id=club_id,
                subgroup_type='club',
                birth_year=0,
            ).order_by(Subgroup.created_at.asc()).first()
        else:
            fallback_subgroup = Subgroup.query.filter_by(
                club_id=club_id,
                subgroup_type=training_scope,
            ).filter(Subgroup.birth_year != 0).order_by(Subgroup.created_at.asc()).first()
            if not fallback_subgroup:
                fallback_subgroup = Subgroup.query.filter_by(
                    club_id=club_id,
                    subgroup_type=training_scope,
                ).order_by(Subgroup.created_at.asc()).first()
        if not fallback_subgroup:
            return jsonify({'error': 'لا توجد مجموعات بنفس نوع التدريب. أضف مجموعة أولاً أو اختر مجموعة.'}), 400
        subgroup_id = fallback_subgroup.id

    try:
        training = Training(
            name=name,
            club_id=club_id,
            subgroup_id=subgroup_id,
            training_scope=training_scope,
            training_date=datetime.fromisoformat(training_date).date(),
            notes=data.get('notes'),
        )
        db.session.add(training)
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
        db.session.delete(training)
        db.session.commit()
        return jsonify({'message': 'تم حذف التدريب بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف التدريب: {str(e)}'}), 500
