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
        return requested_branch_id()

    return user.branch_id


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
    requested_branch = requested_branch_id()

    if user.role == 'branch_manager':
        if not user.branch_id:
            return None, 'حساب مدير الفرع غير مرتبط بفرع'
        return user.branch_id, None

    if user.role in ['admin', 'superadmin']:
        if existing_branches_count > 0 and not requested_branch:
            return None, 'يجب اختيار فرع أولاً قبل الإضافة'
        return requested_branch, None

    return user.branch_id, None
