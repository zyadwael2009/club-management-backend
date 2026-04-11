from flask import Blueprint, request, jsonify, session
from models import db, CheckIn, Player, User, Training, CheckInTraining
from routes.auth import login_required
from datetime import datetime
from zoneinfo import ZoneInfo

checkins_bp = Blueprint('checkins', __name__)

_UTC = ZoneInfo('UTC')
_EGYPT = ZoneInfo('Africa/Cairo')


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


@checkins_bp.route('', methods=['GET'])
@login_required
def get_checkins():
    """Get all check-ins (filtered by club for admin/coach)"""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')
    limit = request.args.get('limit', 50, type=int)
    
    query = CheckIn.query
    
    # Role-based filtering
    if current_user.role == 'admin':
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
    
    checkins = query.order_by(CheckIn.timestamp.desc()).limit(limit).all()
    return jsonify(_append_training_info(checkins))


@checkins_bp.route('/player/<player_id>', methods=['GET'])
@login_required
def get_player_checkins(player_id):
    """Get check-ins for a specific player"""
    current_user = User.query.get(session['user_id'])
    player = Player.query.get(player_id)
    
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    # Check permissions
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player' and player.id != current_user.player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    limit = request.args.get('limit', 20, type=int)
    
    checkins = CheckIn.query.filter_by(player_id=player_id)\
        .order_by(CheckIn.timestamp.desc())\
        .limit(limit).all()

    return jsonify(_append_training_info(checkins))


@checkins_bp.route('', methods=['POST'])
@login_required
def create_checkin():
    """Create a new check-in"""
    data = request.get_json()
    
    if not data or not data.get('playerId'):
        return jsonify({'error': 'معرف اللاعب مطلوب'}), 400

    if not data.get('trainingId'):
        return jsonify({'error': 'يجب اختيار التدريب قبل تسجيل الحضور'}), 400
    
    # Get player to create snapshot
    player = Player.query.get(data['playerId'])
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions (admin/coach can check-in any player in their club)
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا اللاعب'}), 403
    elif current_user.role == 'coach' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا اللاعب'}), 403

    training = Training.query.get(data['trainingId'])
    if not training:
        return jsonify({'error': 'التدريب غير موجود'}), 404

    if training.club_id != player.club_id:
        return jsonify({'error': 'التدريب لا يتبع نفس نادي اللاعب'}), 400
    
    checkin = CheckIn(
        player_id=data['playerId'],
        club_id=data.get('clubId') or player.club_id,
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
