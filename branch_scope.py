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
