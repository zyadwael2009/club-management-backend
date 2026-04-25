from flask import Blueprint, request, jsonify, session
from datetime import datetime
from models import db, Branch, User
from routes.auth import login_required

branches_bp = Blueprint('branches', __name__)


def _can_manage_branches(user):
    return user and user.role in ['admin', 'superadmin']


@branches_bp.route('', methods=['GET'])
@branches_bp.route('/', methods=['GET'])
@login_required
def list_branches():
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')

    query = Branch.query

    if current_user.role == 'superadmin':
        if club_id:
            query = query.filter_by(club_id=club_id)
    elif current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
        if not current_user.branch_id:
            return jsonify([]), 200
        query = query.filter_by(id=current_user.branch_id)
    else:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    rows = query.order_by(Branch.created_at.desc()).all()
    return jsonify([row.to_dict() for row in rows]), 200


@branches_bp.route('/<branch_id>', methods=['GET'])
@branches_bp.route('/<branch_id>/', methods=['GET'])
@login_required
def get_branch(branch_id):
    current_user = User.query.get(session['user_id'])
    branch = Branch.query.get(branch_id)
    if not branch:
        return jsonify({'error': 'الفرع غير موجود'}), 404

    if current_user.role == 'admin' and current_user.club_id != branch.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and current_user.branch_id != branch.id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role not in ['superadmin', 'admin', 'branch_manager']:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    return jsonify(branch.to_dict()), 200


@branches_bp.route('', methods=['POST'])
@branches_bp.route('/', methods=['POST'])
@login_required
def create_branch():
    current_user = User.query.get(session['user_id'])
    if not _can_manage_branches(current_user):
        return jsonify({'error': 'ليس لديك صلاحية لإنشاء الفروع'}), 403

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    club_id = (data.get('clubId') or '').strip()
    manager_username = (data.get('managerUsername') or '').strip()
    manager_password = data.get('managerPassword') or ''

    if not name or not club_id:
        return jsonify({'error': 'اسم الفرع ومعرف النادي مطلوبان'}), 400
    if not manager_username or not manager_password:
        return jsonify({'error': 'اسم المستخدم وكلمة المرور لمدير الفرع مطلوبان'}), 400
    if len(manager_password) < 4:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    if current_user.role == 'admin' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإنشاء فرع لهذا النادي'}), 403

    existing = User.query.filter_by(username=manager_username).first()
    if existing:
        return jsonify({'error': 'اسم مستخدم مدير الفرع موجود بالفعل'}), 400

    try:
        branch = Branch(
            name=name,
            club_id=club_id,
            is_active=bool(data.get('isActive', True)),
        )
        db.session.add(branch)
        db.session.flush()

        manager = User(
            username=manager_username,
            role='branch_manager',
            club_id=club_id,
            branch_id=branch.id,
            is_active=True,
        )
        manager.set_password(manager_password)
        db.session.add(manager)
        db.session.flush()

        branch.manager_user_id = manager.id
        db.session.commit()

        return jsonify({
            'branch': branch.to_dict(),
            'manager': manager.to_dict(),
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء الفرع: {str(e)}'}), 500


@branches_bp.route('/<branch_id>', methods=['PUT'])
@branches_bp.route('/<branch_id>/', methods=['PUT'])
@login_required
def update_branch(branch_id):
    current_user = User.query.get(session['user_id'])
    if not _can_manage_branches(current_user):
        return jsonify({'error': 'ليس لديك صلاحية لتعديل الفروع'}), 403

    branch = Branch.query.get(branch_id)
    if not branch:
        return jsonify({'error': 'الفرع غير موجود'}), 404
    if current_user.role == 'admin' and current_user.club_id != branch.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا الفرع'}), 403

    data = request.get_json() or {}
    if 'name' in data:
        branch.name = (data.get('name') or '').strip() or branch.name
    if 'isActive' in data:
        branch.is_active = bool(data.get('isActive'))
    branch.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(branch.to_dict()), 200


@branches_bp.route('/<branch_id>', methods=['DELETE'])
@branches_bp.route('/<branch_id>/', methods=['DELETE'])
@login_required
def delete_branch(branch_id):
    current_user = User.query.get(session['user_id'])
    if not _can_manage_branches(current_user):
        return jsonify({'error': 'ليس لديك صلاحية لحذف الفروع'}), 403

    branch = Branch.query.get(branch_id)
    if not branch:
        return jsonify({'error': 'الفرع غير موجود'}), 404
    if current_user.role == 'admin' and current_user.club_id != branch.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا الفرع'}), 403

    manager = User.query.filter_by(branch_id=branch.id, role='branch_manager').first()
    if manager:
        db.session.delete(manager)

    db.session.delete(branch)
    db.session.commit()
    return jsonify({'message': 'تم حذف الفرع بنجاح'}), 200
