from flask import Blueprint, request, jsonify, session
from models import db, User, Club, Season
from functools import wraps
from datetime import datetime, date

auth = Blueprint('auth', __name__)


def _current_season_id():
    current = Season.query.filter_by(is_current=True).order_by(Season.updated_at.desc()).first()
    if current:
        return current.id
    fallback = Season.query.order_by(Season.created_at.desc()).first()
    return fallback.id if fallback else None


def _deactivate_club_accounts_if_due(club):
    if not club or not club.due_date:
        return
    if club.due_date >= date.today() or not club.is_active:
        return

    club.is_active = False
    club.deactivated_at = datetime.utcnow()
    users = User.query.filter_by(club_id=club.id).all()
    for user in users:
        if user.role != 'superadmin':
            user.is_active = False
    db.session.commit()


def _enforce_user_and_club_state(user):
    if not user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    if not user.is_active:
        return jsonify({'error': 'حسابك معطل'}), 403

    if user.role != 'superadmin' and user.club_id:
        club = Club.query.get(user.club_id)
        if club:
            _deactivate_club_accounts_if_due(club)
            if not club.is_active:
                return jsonify({'error': 'تم تعطيل حسابات النادي. تواصل مع المدير العام لإعادة التفعيل'}), 403
    return None

# Simple session-based auth (could be upgraded to JWT later)
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 401
        user = User.query.get(session['user_id'])
        state_error = _enforce_user_and_club_state(user)
        if state_error:
            session.clear()
            return state_error
        return f(*args, **kwargs)
    return decorated_function

def admin_or_superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or user.role not in ['admin', 'superadmin', 'branch_manager']:
            return jsonify({'error': 'يجب أن تكون مديراً أو مدير فرع أو مديراً عاماً'}), 403

        state_error = _enforce_user_and_club_state(user)
        if state_error:
            session.clear()
            return state_error
        
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 401
        
        user = User.query.get(session['user_id'])
        if not user or user.role != 'superadmin':
            return jsonify({'error': 'يجب أن تكون المدير العام'}), 403

        state_error = _enforce_user_and_club_state(user)
        if state_error:
            session.clear()
            return state_error
        
        return f(*args, **kwargs)
    return decorated_function


@auth.route('/login', methods=['POST'])
def login():
    """Login endpoint"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'اسم المستخدم وكلمة المرور مطلوبان'}), 400
    
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.check_password(password):
        return jsonify({'error': 'اسم المستخدم أو كلمة المرور غير صحيحة'}), 401

    state_error = _enforce_user_and_club_state(user)
    if state_error:
        return state_error
    
    # Create session
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    
    # Include related data based on role
    response_data = user.to_dict()
    response_data['currentSeasonId'] = _current_season_id()
    
    if user.role == 'admin' and user.club_id:
        club = Club.query.get(user.club_id)
        response_data['club'] = club.to_dict() if club else None
    elif user.role == 'branch_manager' and user.club_id:
        club = Club.query.get(user.club_id)
        response_data['club'] = club.to_dict() if club else None
    
    return jsonify(response_data), 200


@auth.route('/logout', methods=['POST'])
@login_required
def logout():
    """Logout endpoint"""
    session.clear()
    return jsonify({'message': 'تم تسجيل الخروج بنجاح'}), 200


@auth.route('/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current logged-in user"""
    user = User.query.get(session['user_id'])
    
    if not user:
        session.clear()
        return jsonify({'error': 'المستخدم غير موجود'}), 404

    state_error = _enforce_user_and_club_state(user)
    if state_error:
        session.clear()
        return state_error
    
    response_data = user.to_dict()
    response_data['currentSeasonId'] = _current_season_id()
    
    # Include related data based on role
    if user.role == 'admin' and user.club_id:
        club = Club.query.get(user.club_id)
        response_data['club'] = club.to_dict() if club else None
    elif user.role == 'branch_manager' and user.club_id:
        club = Club.query.get(user.club_id)
        response_data['club'] = club.to_dict() if club else None
    
    return jsonify(response_data), 200


@auth.route('/users', methods=['GET'])
@superadmin_required
def list_users():
    """List all users (superadmin only)"""
    users = User.query.all()
    return jsonify([user.to_dict() for user in users]), 200


@auth.route('/users/<user_id>/reset-password', methods=['PUT'])
@admin_or_superadmin_required
def reset_password(user_id):
    """Reset user password (admin can reset users in their club, superadmin can reset anyone)"""
    current_user = User.query.get(session['user_id'])
    target_user = User.query.get(user_id)
    
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    
    # Check permissions
    if current_user.role == 'admin':
        # Admin can only reset passwords for users in their club
        if target_user.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المستخدم'}), 403
    
    data = request.json
    new_password = data.get('newPassword')
    
    if not new_password or len(new_password) < 4:
        return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    
    target_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'message': 'تم تغيير كلمة المرور بنجاح'}), 200


@auth.route('/users/<user_id>/toggle-active', methods=['PUT'])
@admin_or_superadmin_required
def toggle_user_active(user_id):
    """Toggle user active status"""
    current_user = User.query.get(session['user_id'])
    target_user = User.query.get(user_id)
    
    if not target_user:
        return jsonify({'error': 'المستخدم غير موجود'}), 404
    
    # Check permissions
    if current_user.role == 'admin':
        if target_user.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المستخدم'}), 403
    
    # Can't deactivate yourself
    if target_user.id == current_user.id:
        return jsonify({'error': 'لا يمكنك تعطيل حسابك الخاص'}), 400
    
    target_user.is_active = not target_user.is_active

    # If superadmin deactivates an admin, disable all club accounts.
    if current_user.role == 'superadmin' and target_user.role == 'admin' and not target_user.is_active and target_user.club_id:
        affected_users = User.query.filter_by(club_id=target_user.club_id).all()
        for user in affected_users:
            if user.role != 'superadmin':
                user.is_active = False

        club = Club.query.get(target_user.club_id)
        if club:
            club.is_active = False
            club.deactivated_at = datetime.utcnow()

    db.session.commit()
    
    status = 'مفعل' if target_user.is_active else 'معطل'
    return jsonify({'message': f'تم {status} المستخدم بنجاح', 'isActive': target_user.is_active}), 200


@auth.route('/admins/<user_id>/deactivate-cascade', methods=['PUT'])
@superadmin_required
def deactivate_admin_and_club(user_id):
    target_user = User.query.get(user_id)
    if not target_user or target_user.role != 'admin' or not target_user.club_id:
        return jsonify({'error': 'حساب المدير غير موجود'}), 404

    users = User.query.filter_by(club_id=target_user.club_id).all()
    for user in users:
        if user.role != 'superadmin':
            user.is_active = False

    club = Club.query.get(target_user.club_id)
    if club:
        club.is_active = False
        club.deactivated_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'message': 'تم تعطيل المدير وكل حسابات النادي'}), 200
