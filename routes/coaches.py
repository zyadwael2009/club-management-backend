from flask import Blueprint, request, jsonify, session
from models import db, Coach, User, CoachPayment, CoachCheckIn
from routes.auth import login_required, admin_or_superadmin_required
from branch_scope import effective_branch_id_for_user, resolve_creation_branch_for_user
from season_context import get_effective_season_id
from werkzeug.utils import secure_filename
import os
from datetime import datetime

coaches = Blueprint('coaches', __name__)

UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')


@coaches.route('', methods=['GET'])
@login_required
def list_coaches():
    """List all coaches (filtered by club for admin)"""
    current_user = User.query.get(session['user_id'])
    
    branch_id = effective_branch_id_for_user(current_user)

    if current_user.role == 'superadmin':
        # Superadmin sees all coaches
        club_id = request.args.get('clubId')
        query = Coach.query
        if club_id:
            query = query.filter_by(club_id=club_id)
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        coaches_list = query.all()
    elif current_user.role == 'admin':
        # Admin sees only their club's coaches
        query = Coach.query.filter_by(club_id=current_user.club_id)
        if branch_id:
            query = query.filter_by(branch_id=branch_id)
        coaches_list = query.all()
    elif current_user.role == 'branch_manager':
        coaches_list = Coach.query.filter_by(
            club_id=current_user.club_id,
            branch_id=current_user.branch_id,
        ).all()
    else:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify([coach.to_dict() for coach in coaches_list]), 200


@coaches.route('/<coach_id>', methods=['GET'])
@login_required
def get_coach(coach_id):
    """Get a single coach"""
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and current_user.coach_id != coach_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify(coach.to_dict()), 200


@coaches.route('', methods=['POST'])
@admin_or_superadmin_required
def create_coach():
    """Create a new coach (admin/superadmin only)"""
    current_user = User.query.get(session['user_id'])
    data = request.json
    
    # Validate required fields
    if not data.get('fullName'):
        return jsonify({'error': 'اسم المدرب مطلوب'}), 400
    
    if not data.get('clubId'):
        return jsonify({'error': 'النادي مطلوب'}), 400
    
    # Admin can only create coaches for their club
    if current_user.role == 'admin' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مدربين لهذا النادي'}), 403
    if current_user.role == 'branch_manager' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مدربين لهذا النادي'}), 403
    branch_id, branch_error = resolve_creation_branch_for_user(current_user, data['clubId'])
    if branch_error:
        return jsonify({'error': branch_error}), 400
    
    # Check if username is provided and unique
    username = data.get('username')
    password = data.get('password')
    
    if username:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
        
        if not password or len(password) < 4:
            return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
    
    try:
        # Create coach
        coach = Coach(
            full_name=data['fullName'],
            club_id=data['clubId'],
            branch_id=branch_id,
            is_active=bool(data.get('isActive', True)),
            monthly_salary=data.get('monthlySalary'),
            contact_info=data.get('contactInfo'),
            notes=data.get('notes'),
            image_url=data.get('imageUrl')
        )
        db.session.add(coach)
        db.session.flush()  # Get the coach ID
        
        # Create user if username provided
        if username:
            user = User(
                username=username,
                role='coach',
                club_id=data['clubId'],
                branch_id=branch_id,
                coach_id=coach.id
            )
            user.set_password(password)
            db.session.add(user)
        
        db.session.commit()
        return jsonify(coach.to_dict()), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إنشاء المدرب: {str(e)}'}), 500


@coaches.route('/<coach_id>', methods=['PUT'])
@admin_or_superadmin_required
def update_coach(coach_id):
    """Update a coach"""
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only update their club's coaches
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المدرب'}), 403
    if current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المدرب'}), 403
    
    data = request.json
    
    try:
        # Update coach fields
        if 'fullName' in data:
            coach.full_name = data['fullName']
        if 'monthlySalary' in data:
            coach.monthly_salary = data['monthlySalary']
        if 'contactInfo' in data:
            coach.contact_info = data['contactInfo']
        if 'notes' in data:
            coach.notes = data['notes']
        if 'imageUrl' in data:
            coach.image_url = data['imageUrl']
        if 'isActive' in data:
            coach.is_active = bool(data['isActive'])
            coach.deactivated_at = None if coach.is_active else datetime.utcnow()
        
        coach.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(coach.to_dict()), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل تحديث المدرب: {str(e)}'}), 500


@coaches.route('/<coach_id>/toggle-active', methods=['PUT'])
@admin_or_superadmin_required
def toggle_coach_active(coach_id):
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المدرب'}), 403
    if current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذا المدرب'}), 403

    data = request.get_json() or {}
    make_active = data.get('isActive')
    if make_active is None:
        make_active = not bool(coach.is_active)
    coach.is_active = bool(make_active)
    coach.deactivated_at = None if coach.is_active else datetime.utcnow()
    coach.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(coach.to_dict()), 200


@coaches.route('/<coach_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_coach(coach_id):
    """Delete a coach"""
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404
    if not bool(coach.is_active):
        return jsonify({'error': 'لا يمكن تسجيل حضور مدرب غير نشط'}), 400
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only delete their club's coaches
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المدرب'}), 403
    if current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المدرب'}), 403
    
    try:
        # Delete associated user if exists
        user = User.query.filter_by(coach_id=coach_id).first()
        if user:
            db.session.delete(user)
        
        # Delete coach
        db.session.delete(coach)
        db.session.commit()
        
        return jsonify({'message': 'تم حذف المدرب بنجاح'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف المدرب: {str(e)}'}), 500


# ==================== COACH PAYMENTS ====================

@coaches.route('/<coach_id>/payments', methods=['GET'])
@login_required
def get_coach_payments(coach_id):
    """Get payment history for a coach"""
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and current_user.coach_id != coach_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    season_id = get_effective_season_id(default_to_current=True)
    query = CoachPayment.query.filter_by(coach_id=coach_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    payments = query.order_by(CoachPayment.payment_date.desc()).all()
    return jsonify([payment.to_dict() for payment in payments]), 200


@coaches.route('/payments/club/<club_id>', methods=['GET'])
@login_required
def get_club_coach_payments(club_id):
    """Get all coach salary payments for a club."""
    current_user = User.query.get(session['user_id'])

    if current_user.role == 'admin' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'player':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    season_id = get_effective_season_id(default_to_current=True)

    rows = (
        db.session.query(CoachPayment, Coach)
        .join(Coach, CoachPayment.coach_id == Coach.id)
        .filter(Coach.club_id == club_id)
        .filter(CoachPayment.season_id == season_id if season_id else True)
        .order_by(CoachPayment.payment_date.desc())
        .all()
    )
    if current_user.role == 'branch_manager':
        rows = [(payment, coach) for payment, coach in rows if payment.branch_id == current_user.branch_id]

    result = []
    for payment, coach in rows:
        item = payment.to_dict()
        item['coachName'] = coach.full_name
        item['clubId'] = coach.club_id
        result.append(item)

    return jsonify(result), 200


@coaches.route('/<coach_id>/payments', methods=['POST'])
@admin_or_superadmin_required
def add_coach_payment(coach_id):
    """Record a salary payment to a coach"""
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only add payments for their club's coaches
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة دفعات لهذا المدرب'}), 403
    if current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة دفعات لهذا المدرب'}), 403
    
    data = request.json
    
    if not data.get('amount') or not data.get('paymentDate') or not data.get('paymentMonth'):
        return jsonify({'error': 'المبلغ وتاريخ الدفع والشهر مطلوبون'}), 400
    
    try:
        season_id = get_effective_season_id(default_to_current=True)
        expense_scope = data.get('expenseScope', 'club')
        if expense_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع المصروف يجب أن يكون club أو academy'}), 400

        payment = CoachPayment(
            coach_id=coach_id,
            branch_id=coach.branch_id,
            season_id=season_id,
            amount=float(data['amount']),
            payment_date=datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date(),
            payment_month=data['paymentMonth'],
            expense_scope=expense_scope,
            notes=data.get('notes')
        )
        db.session.add(payment)
        db.session.commit()
        
        return jsonify(payment.to_dict()), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إضافة الدفعة: {str(e)}'}), 500


@coaches.route('/<coach_id>/payments/<payment_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_coach_payment(coach_id, payment_id):
    """Delete a coach payment record"""
    payment = CoachPayment.query.get(payment_id)
    if not payment or payment.coach_id != coach_id:
        return jsonify({'error': 'الدفعة غير موجودة'}), 404
    
    coach = Coach.query.get(coach_id)
    current_user = User.query.get(session['user_id'])
    
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه الدفعة'}), 403
    if current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه الدفعة'}), 403
    
    try:
        db.session.delete(payment)
        db.session.commit()
        return jsonify({'message': 'تم حذف الدفعة بنجاح'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف الدفعة: {str(e)}'}), 500


# ==================== COACH QR & CHECK-INS ====================

@coaches.route('/qr/<qr_code>', methods=['GET'])
@login_required
def get_coach_by_qr(qr_code):
    if not qr_code.startswith('CLUB_COACH_'):
        return jsonify({'error': 'Invalid QR code format'}), 400

    coach_id = qr_code.replace('CLUB_COACH_', '')
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and current_user.coach_id != coach_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    return jsonify(coach.to_dict()), 200


@coaches.route('/checkins', methods=['POST'])
@login_required
def create_coach_checkin():
    data = request.get_json() or {}
    coach_id = data.get('coachId')
    if not coach_id:
        return jsonify({'error': 'معرف المدرب مطلوب'}), 400

    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا المدرب'}), 403
    elif current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا المدرب'}), 403
    elif current_user.role == 'coach' and current_user.coach_id != coach.id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا المدرب'}), 403

    season_id = get_effective_season_id(default_to_current=True)

    record = CoachCheckIn(
        coach_id=coach.id,
        club_id=coach.club_id,
        branch_id=coach.branch_id,
        season_id=season_id,
        coach_name=coach.full_name,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@coaches.route('/<coach_id>/checkins', methods=['GET'])
@login_required
def get_coach_checkins(coach_id):
    coach = Coach.query.get(coach_id)
    if not coach:
        return jsonify({'error': 'المدرب غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and coach.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and coach.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and current_user.coach_id != coach_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    limit = request.args.get('limit', 20, type=int)
    season_id = get_effective_season_id(default_to_current=True)
    query = CoachCheckIn.query.filter_by(coach_id=coach_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    rows = query.order_by(CoachCheckIn.timestamp.desc()).limit(limit).all()
    return jsonify([row.to_dict() for row in rows]), 200
