from flask import Blueprint, request, jsonify, session
from models import db, Subgroup, Club, User, Player
from routes.auth import login_required, admin_or_superadmin_required

subgroups_bp = Blueprint('subgroups', __name__)


@subgroups_bp.route('/', methods=['GET'])
@login_required
def get_subgroups():
    """Get all subgroups (filtered by club for admin/coach)"""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')
    
    query = Subgroup.query
    
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
    
    subgroups = query.order_by(Subgroup.birth_year.desc()).all()
    return jsonify([sg.to_dict() for sg in subgroups])


@subgroups_bp.route('/<subgroup_id>', methods=['GET'])
@login_required
def get_subgroup(subgroup_id):
    """Get a specific subgroup by ID"""
    subgroup = Subgroup.query.get(subgroup_id)
    if not subgroup:
        return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and subgroup.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and subgroup.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify(subgroup.to_dict())


@subgroups_bp.route('/', methods=['POST'])
@admin_or_superadmin_required
def create_subgroup():
    """Create a new subgroup (admin/superadmin only)"""
    current_user = User.query.get(session['user_id'])
    data = request.get_json()
    
    if not data.get('clubId'):
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    
    # Admin can only create subgroups for their club
    if current_user.role == 'admin' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مجموعات لهذا النادي'}), 403
    
    if not data.get('subgroupType'):
        return jsonify({'error': 'نوع المجموعة مطلوب (أكاديمية أو نادي)'}), 400
    
    if data.get('birthYear') is None:
        return jsonify({'error': 'سنة الميلاد مطلوبة'}), 400

    monthly_amount = data.get('monthlyAmount')
    if data.get('subgroupType') == 'academy':
        if monthly_amount is None:
            return jsonify({'error': 'المبلغ الشهري مطلوب لمجموعة الأكاديمية'}), 400
        try:
            monthly_amount = float(monthly_amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'المبلغ الشهري غير صالح'}), 400
        if monthly_amount <= 0:
            return jsonify({'error': 'المبلغ الشهري يجب أن يكون أكبر من صفر'}), 400
    
    # Verify club exists
    club = Club.query.get(data['clubId'])
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    try:
        birth_year = int(data.get('birthYear'))
    except (TypeError, ValueError):
        return jsonify({'error': 'سنة الميلاد يجب أن تكون رقمية'}), 400

    # Generate name based on type and year (0 means first team)
    if birth_year == 0:
        default_name = 'الفريق الاول'
    else:
        type_name = 'أكاديمية' if data['subgroupType'] == 'academy' else 'نادي'
        default_name = f"{type_name} {birth_year}"

    name = data.get('name') or default_name
    
    subgroup = Subgroup(
        name=name,
        club_id=data['clubId'],
        subgroup_type=data['subgroupType'],
        birth_year=birth_year,
        monthly_amount=monthly_amount if data['subgroupType'] == 'academy' else None,
        description=data.get('description')
    )
    
    db.session.add(subgroup)
    db.session.commit()
    
    return jsonify(subgroup.to_dict()), 201


@subgroups_bp.route('/<subgroup_id>', methods=['PUT'])
@admin_or_superadmin_required
def update_subgroup(subgroup_id):
    """Update a subgroup (admin/superadmin only)"""
    subgroup = Subgroup.query.get(subgroup_id)
    if not subgroup:
        return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only update their club's subgroups
    if current_user.role == 'admin' and subgroup.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذه المجموعة'}), 403
    
    data = request.get_json()
    
    if 'name' in data:
        subgroup.name = data['name']
    if 'subgroupType' in data:
        subgroup.subgroup_type = data['subgroupType']
    if 'birthYear' in data:
        try:
            subgroup.birth_year = int(data['birthYear'])
        except (TypeError, ValueError):
            return jsonify({'error': 'سنة الميلاد يجب أن تكون رقمية'}), 400
    if 'description' in data:
        subgroup.description = data['description']

    if subgroup.subgroup_type == 'academy':
        if 'monthlyAmount' in data:
            try:
                subgroup.monthly_amount = float(data['monthlyAmount']) if data['monthlyAmount'] is not None else None
            except (TypeError, ValueError):
                return jsonify({'error': 'المبلغ الشهري غير صالح'}), 400
        if subgroup.monthly_amount is None or subgroup.monthly_amount <= 0:
            return jsonify({'error': 'المبلغ الشهري مطلوب لمجموعة الأكاديمية'}), 400
    else:
        subgroup.monthly_amount = None

    # Keep players in subgroup aligned with subgroup monthly amount.
    if subgroup.subgroup_type == 'academy' and subgroup.monthly_amount is not None:
        players = Player.query.filter_by(subgroup_id=subgroup.id).all()
        for player in players:
            player.monthly_amount = subgroup.monthly_amount
    
    db.session.commit()
    return jsonify(subgroup.to_dict())


@subgroups_bp.route('/<subgroup_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_subgroup(subgroup_id):
    """Delete a subgroup (admin/superadmin only)"""
    subgroup = Subgroup.query.get(subgroup_id)
    if not subgroup:
        return jsonify({'error': 'المجموعة الفرعية غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only delete their club's subgroups
    if current_user.role == 'admin' and subgroup.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه المجموعة'}), 403
    
    db.session.delete(subgroup)
    db.session.commit()
    
    return jsonify({'message': 'تم حذف المجموعة الفرعية بنجاح'})


@subgroups_bp.route('/club/<club_id>', methods=['GET'])
def get_club_subgroups(club_id):
    """Get all subgroups for a specific club"""
    club = Club.query.get(club_id)
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    subgroups = Subgroup.query.filter_by(club_id=club_id).order_by(Subgroup.birth_year.desc()).all()
    return jsonify([sg.to_dict() for sg in subgroups])
