from flask import request


def requested_branch_id():
    """Branch context requested by admin (header first, then query)."""
    header_value = (request.headers.get('X-Branch-Id') or '').strip()
    if header_value:
        return header_value
    query_value = (request.args.get('branch_id') or '').strip()
    return query_value or None


def effective_branch_id_for_user(user):
    """
    Resolve effective branch scope:
    - branch_manager: always own branch
    - admin/superadmin: optional selected branch from request
    - others: own branch if set, else no branch filter
    """
    if not user:
        return None

    if user.role == 'branch_manager':
        return user.branch_id

    if user.role in ['admin', 'superadmin']:
        validated_branch, _ = _validate_requested_branch_for_user(user)
        return validated_branch

    return user.branch_id


def _validate_requested_branch_for_user(user, club_id=None):
    """
    Validate requested branch from header/query against DB and optional club scope.
    Returns: (branch_id, error_message)
    """
    requested_branch = requested_branch_id()
    if not requested_branch:
        return None, None

    from models import Branch

    branch = Branch.query.get(requested_branch)
    if not branch:
        return None, 'الفرع المحدد غير موجود'

    if club_id and branch.club_id != club_id:
        return None, 'الفرع المحدد لا يتبع هذا النادي'

    if user and user.role == 'admin' and user.club_id and branch.club_id != user.club_id:
        return None, 'ليس لديك صلاحية لاختيار هذا الفرع'

    return branch.id, None


def resolve_creation_branch_for_user(user, club_id):
    """
    Resolve branch for create operations and enforce required selection rules.
    Returns: (branch_id, error_message)
    """
    if not user:
        return None, 'المستخدم غير موجود'

    from models import Branch

    if not club_id:
        return None, 'معرف النادي مطلوب'

    existing_branches_count = Branch.query.filter_by(club_id=club_id).count()
    requested_branch, requested_error = _validate_requested_branch_for_user(user, club_id=club_id)

    if user.role == 'branch_manager':
        if not user.branch_id:
            return None, 'حساب مدير الفرع غير مرتبط بفرع'

        manager_branch = Branch.query.get(user.branch_id)
        if not manager_branch:
            return None, 'الفرع المرتبط بحساب مدير الفرع غير موجود'
        if manager_branch.club_id != club_id:
            return None, 'فرع مدير الفرع لا يتبع النادي المحدد'

        return manager_branch.id, None

    if user.role in ['admin', 'superadmin']:
        if requested_error:
            return None, requested_error
        if existing_branches_count > 0 and not requested_branch:
            return None, 'يجب اختيار فرع أولاً قبل الإضافة'
        return requested_branch, None

    if user.branch_id:
        user_branch = Branch.query.get(user.branch_id)
        if not user_branch:
            return None, 'الفرع المرتبط بالمستخدم غير موجود'
        if user_branch.club_id != club_id:
            return None, 'الفرع المرتبط بالمستخدم لا يتبع النادي المحدد'
        return user_branch.id, None

    return None, None
