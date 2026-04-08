from flask import Blueprint, request, jsonify, session
from models import db, Training, Subgroup, User
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime

trainings_bp = Blueprint('trainings', __name__)


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
    training_date = data.get('trainingDate')

    if not name:
        return jsonify({'error': 'اسم التدريب مطلوب'}), 400
    if not club_id:
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    if not training_date:
        return jsonify({'error': 'تاريخ التدريب مطلوب'}), 400

    if current_user.role == 'admin' and club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة تدريب لهذا النادي'}), 403

    if subgroup_id:
        subgroup = Subgroup.query.get(subgroup_id)
        if not subgroup:
            return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
        if subgroup.club_id != club_id:
            return jsonify({'error': 'المجموعة الفرعية لا تتبع هذا النادي'}), 400
    else:
        # Keep DB compatibility where subgroup may still be non-null by defaulting to first subgroup.
        fallback_subgroup = Subgroup.query.filter_by(club_id=club_id).order_by(Subgroup.created_at.asc()).first()
        if not fallback_subgroup:
            return jsonify({'error': 'لا توجد مجموعات فرعية في النادي. أضف مجموعة أولاً أو اختر مجموعة.'}), 400
        subgroup_id = fallback_subgroup.id

    try:
        training = Training(
            name=name,
            club_id=club_id,
            subgroup_id=subgroup_id,
            training_date=datetime.fromisoformat(training_date).date(),
            notes=data.get('notes'),
        )
        db.session.add(training)
        db.session.commit()
        return jsonify(training.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء التدريب: {str(e)}'}), 500


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
