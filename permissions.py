import json

COACH_PERMISSION_KEYS = [
    'dashboard',
    'players',
    'coaches',
    'checkin_scanner',
    'checkin_history',
    'trainings',
    'matches',
    'subgroups',
    'payments',
    'academy_renewals',
    'employees',
    'branches',
    'seasons',
    'club_settings',
]

DEFAULT_COACH_PERMISSIONS = list(COACH_PERMISSION_KEYS)


def normalize_permissions(raw, default_to_all=True):
    if raw is None:
        return DEFAULT_COACH_PERMISSIONS.copy() if default_to_all else []

    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [raw]

    if isinstance(raw, list):
        return [p for p in raw if p in COACH_PERMISSION_KEYS]

    return DEFAULT_COACH_PERMISSIONS.copy() if default_to_all else []


def parse_permissions(value, default=None):
    if value in [None, '']:
        return default if default is not None else []

    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else []

    if not isinstance(parsed, list):
        return default if default is not None else []

    return [p for p in parsed if p in COACH_PERMISSION_KEYS]


def serialize_permissions(raw, default_to_all=True):
    permissions = normalize_permissions(raw, default_to_all=default_to_all)
    return json.dumps(permissions)
