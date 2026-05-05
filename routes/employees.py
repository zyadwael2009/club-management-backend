from flask import Blueprint, request, jsonify, session
from models import db, Employee, EmployeePayment, EmployeeCheckIn, User
from routes.auth import login_required, ensure_coach_permission
from season_context import get_effective_season_id
from flask_cors import CORS
import uuid
from datetime import datetime

employees_bp = Blueprint('employees', __name__)


def _parse_payment_date(value):
    if not value:
        return None
    if isinstance(value, str):
        normalized = value.replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return None
    return None


def _require_employee_access(allow_employee=False):
    current_user = User.query.get(session.get('user_id')) if 'user_id' in session else None
    if not current_user:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), None

    permission_error = ensure_coach_permission(current_user, 'employees')
    if permission_error:
        return permission_error, None

    allowed_roles = ['superadmin', 'admin', 'branch_manager', 'coach']
    if allow_employee:
        allowed_roles.append('employee')

    if current_user.role not in allowed_roles:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), None

    return None, current_user

@employees_bp.route('/', methods=['GET'], strict_slashes=False)
@login_required
def get_employees():
    print("DEBUG: Entering get_employees")
    club_id = request.args.get('clubId')
    if not club_id:
        print("DEBUG: clubId is missing")
        return jsonify({'error': 'clubId is required'}), 400

    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    if current_user.role in ['admin', 'branch_manager', 'coach'] and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    try:
        print(f"DEBUG: Fetching employees for club {club_id}")
        employees = Employee.query.filter_by(club_id=club_id).all()
        print(f"DEBUG: Found {len(employees)} employees")
        return jsonify([e.to_dict() for e in employees])
    except Exception as e:
        print(f"DEBUG: Error in get_employees: {str(e)}")
        return jsonify({'error': str(e)}), 500

@employees_bp.route('/<id>', methods=['GET'], strict_slashes=False)
@login_required
def get_employee(id):
    print(f"DEBUG: Entering get_employee for {id}")
    access_error, current_user = _require_employee_access(allow_employee=True)
    if access_error:
        return access_error
    try:
        employee = Employee.query.get(id)
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        if current_user.role in ['admin', 'branch_manager', 'coach'] and employee.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
        if current_user.role == 'employee' and current_user.employee_id != employee.id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
        return jsonify(employee.to_dict())
    except Exception as e:
        print(f"DEBUG: Error in get_employee: {str(e)}")
        return jsonify({'error': str(e)}), 500

@employees_bp.route('/', methods=['POST'], strict_slashes=False)
@login_required
def create_employee():
    print("DEBUG: Entering create_employee")
    data = request.get_json()
    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    if current_user.role in ['admin', 'branch_manager', 'coach'] and data.get('clubId') != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    try:
        username = (data.get('username') or '').strip()
        password = data.get('password')
        if username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
            if not password or len(password) < 4:
                return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400

        employee = Employee(
            full_name=data['fullName'],
            club_id=data['clubId'],
            branch_id=data.get('branchId'),
            role=data['role'],
            monthly_salary=data.get('monthlySalary'),
            contact_info=data.get('contactInfo'),
            notes=data.get('notes'),
            image_url=data.get('imageUrl'),
        )
        db.session.add(employee)

        if username:
            user = User(
                username=username,
                role='employee',
                club_id=employee.club_id,
                employee_id=employee.id,
            )
            user.set_password(password)
            db.session.add(user)

        db.session.commit()
        return jsonify(employee.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in create_employee: {str(e)}")
        return jsonify({'error': str(e)}), 400

@employees_bp.route('/<id>', methods=['PUT'], strict_slashes=False)
@login_required
def update_employee(id):
    print(f"DEBUG: Entering update_employee for {id}")
    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    try:
        employee = Employee.query.get(id)
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        if current_user.role in ['admin', 'branch_manager', 'coach'] and employee.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        password = data.get('password')
        user = User.query.filter_by(employee_id=employee.id).first()
        employee.full_name = data.get('fullName', employee.full_name)
        employee.role = data.get('role', employee.role)
        employee.monthly_salary = data.get('monthlySalary', employee.monthly_salary)
        employee.contact_info = data.get('contactInfo', employee.contact_info)
        employee.notes = data.get('notes', employee.notes)
        employee.image_url = data.get('imageUrl', employee.image_url)
        employee.is_active = data.get('isActive', employee.is_active)
        employee.branch_id = data.get('branchId', employee.branch_id)

        if username:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user and (user is None or existing_user.id != user.id):
                return jsonify({'error': 'اسم المستخدم موجود بالفعل'}), 400
            if user:
                user.username = username
            else:
                user = User(
                    username=username,
                    role='employee',
                    club_id=employee.club_id,
                    branch_id=employee.branch_id,
                    employee_id=employee.id,
                    is_active=employee.is_active,
                )
                db.session.add(user)

        if password:
            if len(password) < 4:
                return jsonify({'error': 'كلمة المرور يجب أن تكون 4 أحرف على الأقل'}), 400
            if not user:
                return jsonify({'error': 'اسم المستخدم مطلوب لتحديث كلمة المرور'}), 400
            user.set_password(password)

        if user:
            user.is_active = employee.is_active

        db.session.commit()
        return jsonify(employee.to_dict())
    except Exception as e:
        print(f"DEBUG: Error in update_employee: {str(e)}")
        return jsonify({'error': str(e)}), 500


@employees_bp.route('/qr/<qr_code>', methods=['GET'], strict_slashes=False)
@login_required
def get_employee_by_qr(qr_code):
    raw_code = (qr_code or '').strip()
    employee = None
    if raw_code.startswith('CLUB_EMPLOYEE_'):
        employee_id = raw_code.replace('CLUB_EMPLOYEE_', '')
        employee = Employee.query.get(employee_id)
    else:
        employee = Employee.query.get(raw_code)
    if not employee:
        return jsonify({'error': 'الموظف غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_scanner')
    if permission_error:
        return permission_error

    if current_user.role == 'admin' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and employee.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'employee' and current_user.employee_id != employee.id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    return jsonify(employee.to_dict()), 200


@employees_bp.route('/checkins', methods=['POST'], strict_slashes=False)
@login_required
def create_employee_checkin():
    data = request.get_json() or {}
    employee_id = data.get('employeeId')
    if not employee_id:
        return jsonify({'error': 'معرف الموظف مطلوب'}), 400

    employee = Employee.query.get(employee_id)
    if not employee:
        return jsonify({'error': 'الموظف غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    permission_error = ensure_coach_permission(current_user, 'checkin_scanner')
    if permission_error:
        return permission_error

    if current_user.role == 'admin' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا الموظف'}), 403
    if current_user.role == 'branch_manager' and employee.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا الموظف'}), 403
    if current_user.role == 'coach' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا الموظف'}), 403
    if current_user.role == 'employee' and current_user.employee_id != employee.id:
        return jsonify({'error': 'ليس لديك صلاحية للتسجيل لهذا الموظف'}), 403

    season_id = get_effective_season_id(default_to_current=True)

    record = EmployeeCheckIn(
        employee_id=employee.id,
        club_id=employee.club_id,
        branch_id=employee.branch_id,
        season_id=season_id,
        employee_name=employee.full_name,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify(record.to_dict()), 201


@employees_bp.route('/<id>/checkins', methods=['GET'], strict_slashes=False)
@login_required
def get_employee_checkins(id):
    employee = Employee.query.get(id)
    if not employee:
        return jsonify({'error': 'الموظف غير موجود'}), 404

    current_user = User.query.get(session['user_id'])
    if current_user.role != 'employee' or current_user.employee_id != id:
        permission_error = ensure_coach_permission(current_user, 'checkin_history')
        if permission_error:
            return permission_error

    if current_user.role == 'admin' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and employee.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and employee.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'employee' and current_user.employee_id != id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    limit = request.args.get('limit', 20, type=int)
    season_id = get_effective_season_id(default_to_current=True)
    query = EmployeeCheckIn.query.filter_by(employee_id=id)
    if season_id:
        query = query.filter_by(season_id=season_id)

    rows = query.order_by(EmployeeCheckIn.timestamp.desc()).limit(limit).all()
    return jsonify([row.to_dict() for row in rows]), 200

@employees_bp.route('/<id>', methods=['DELETE'], strict_slashes=False)
@login_required
def delete_employee(id):
    print(f"DEBUG: Entering delete_employee for {id}")
    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    try:
        employee = Employee.query.get(id)
        if not employee:
            return jsonify({'error': 'Employee not found'}), 404
        if current_user.role in ['admin', 'branch_manager', 'coach'] and employee.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

        db.session.delete(employee)
        db.session.commit()
        return jsonify({'message': 'Employee deleted successfully'}), 200
    except Exception as e:
        print(f"DEBUG: Error in delete_employee: {str(e)}")
        return jsonify({'error': str(e)}), 500

@employees_bp.route('/<id>/payments', methods=['GET'], strict_slashes=False)
@login_required
def get_employee_payments(id):
    print(f"DEBUG: Entering get_employee_payments for {id}")
    access_error, current_user = _require_employee_access(allow_employee=True)
    if access_error:
        return access_error
    try:
        payments = EmployeePayment.query.filter_by(employee_id=id).all()
        if current_user.role in ['admin', 'branch_manager', 'coach']:
            employee = Employee.query.get(id)
            if employee and employee.club_id != current_user.club_id:
                return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
        if current_user.role == 'employee' and current_user.employee_id != id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
        return jsonify([p.to_dict() for p in payments])
    except Exception as e:
        print(f"DEBUG: Error in get_employee_payments: {str(e)}")
        return jsonify({'error': str(e)}), 500

@employees_bp.route('/<id>/payments', methods=['POST'], strict_slashes=False)
@login_required
def add_employee_payment(id):
    print(f"DEBUG: Entering add_employee_payment for {id}")
    data = request.get_json()
    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    try:
        amount_value = data.get('amount')
        payment_date = _parse_payment_date(data.get('paymentDate'))
        if amount_value is None or payment_date is None:
            return jsonify({'error': 'amount and paymentDate are required'}), 400

        employee = Employee.query.get(id)
        if employee and current_user.role in ['admin', 'branch_manager', 'coach'] and employee.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

        payment_month = data.get('paymentMonth')
        if not payment_month:
            payment_month = payment_date.strftime('%Y-%m')

        payment = EmployeePayment(
            employee_id=id,
            branch_id=data.get('branchId') or request.headers.get('X-Branch-Id'),
            season_id=data.get('seasonId') or request.headers.get('X-Season-Id'),
            amount=float(amount_value),
            payment_date=payment_date,
            payment_month=payment_month,
            expense_scope=data.get('expenseScope', 'club'),
            notes=data.get('notes'),
        )
        db.session.add(payment)
        db.session.commit()
        return jsonify(payment.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: Error in add_employee_payment: {str(e)}")
        return jsonify({'error': str(e)}), 400

@employees_bp.route('/<id>/payments/<payment_id>', methods=['DELETE'], strict_slashes=False)
@login_required
def delete_employee_payment(id, payment_id):
    print(f"DEBUG: Entering delete_employee_payment {payment_id} for {id}")
    access_error, current_user = _require_employee_access()
    if access_error:
        return access_error
    try:
        payment = EmployeePayment.query.get(payment_id)
        if not payment or payment.employee_id != id:
            return jsonify({'error': 'Payment not found'}), 404

        employee = Employee.query.get(id)
        if employee and current_user.role in ['admin', 'branch_manager', 'coach'] and employee.club_id != current_user.club_id:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

        db.session.delete(payment)
        db.session.commit()
        return jsonify({'message': 'Payment deleted successfully'}), 200
    except Exception as e:
        print(f"DEBUG: Error in delete_employee_payment: {str(e)}")
        return jsonify({'error': str(e)}), 500
