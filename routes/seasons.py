from flask import Blueprint, request, jsonify, session
from models import db, Season, User
from routes.auth import login_required, superadmin_required
from datetime import datetime

seasons_bp = Blueprint('seasons', __name__)


def _ensure_single_current_season():
    seasons = Season.query.order_by(Season.created_at.asc()).all()
    if not seasons:
        return None

    current_seasons = [season for season in seasons if season.is_current]
    if len(current_seasons) == 1:
        return current_seasons[0]

    if not current_seasons:
        fallback = seasons[-1]
        fallback.is_current = True
        db.session.commit()
        return fallback

    keep = sorted(current_seasons, key=lambda s: s.updated_at or s.created_at)[-1]
    for season in current_seasons:
        season.is_current = season.id == keep.id
    db.session.commit()
    return keep


@seasons_bp.route('', methods=['GET'])
@login_required
def list_seasons():
    _ensure_single_current_season()
    seasons = Season.query.order_by(Season.created_at.desc()).all()
    return jsonify([season.to_dict() for season in seasons]), 200


@seasons_bp.route('/current', methods=['GET'])
@login_required
def get_current_season():
    current = _ensure_single_current_season()
    if not current:
        return jsonify({'error': 'لا توجد مواسم بعد'}), 404
    return jsonify(current.to_dict()), 200


@seasons_bp.route('', methods=['POST'])
@superadmin_required
def create_season():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()

    if not name:
        return jsonify({'error': 'اسم الموسم مطلوب'}), 400

    if Season.query.filter(Season.name.ilike(name)).first():
        return jsonify({'error': 'اسم الموسم موجود بالفعل'}), 400

    should_be_current = bool(data.get('isCurrent', False))
    has_existing = Season.query.count() > 0
    if not has_existing:
        should_be_current = True

    current_user = User.query.get(session['user_id'])

    try:
        if should_be_current:
            Season.query.update({'is_current': False})

        season = Season(
            name=name,
            is_current=should_be_current,
            created_by_user_id=current_user.id if current_user else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(season)
        db.session.commit()

        return jsonify(season.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء الموسم: {str(e)}'}), 500


@seasons_bp.route('/<season_id>', methods=['PUT'])
@superadmin_required
def update_season(season_id):
    season = Season.query.get(season_id)
    if not season:
        return jsonify({'error': 'الموسم غير موجود'}), 404

    data = request.get_json() or {}

    if 'name' in data:
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return jsonify({'error': 'اسم الموسم مطلوب'}), 400

        duplicate = Season.query.filter(Season.name.ilike(new_name), Season.id != season.id).first()
        if duplicate:
            return jsonify({'error': 'اسم الموسم موجود بالفعل'}), 400

        season.name = new_name

    if 'isCurrent' in data:
        is_current = bool(data['isCurrent'])
        if is_current:
            Season.query.update({'is_current': False})
            season.is_current = True
        else:
            if season.is_current:
                another_current = Season.query.filter(Season.id != season.id, Season.is_current == True).first()
                if not another_current:
                    return jsonify({'error': 'يجب أن يبقى موسم حالي واحد على الأقل'}), 400
            season.is_current = False

    season.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        _ensure_single_current_season()
        return jsonify(season.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل تحديث الموسم: {str(e)}'}), 500
