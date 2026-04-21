from flask import request
from models import Season


def get_current_season():
    current = Season.query.filter_by(is_current=True).order_by(Season.updated_at.desc()).first()
    if current:
        return current
    return Season.query.order_by(Season.created_at.desc()).first()


def get_effective_season(default_to_current=True):
    raw_value = request.args.get('season_id') or request.headers.get('X-Season-Id')
    if raw_value:
        season_id = raw_value.strip()
        if season_id:
            if season_id.lower() in ['current', 'default']:
                return get_current_season()
            season = Season.query.get(season_id)
            if season is not None:
                return season
            if default_to_current:
                return get_current_season()
            return None

    if default_to_current:
        return get_current_season()
    return None


def get_effective_season_id(default_to_current=True):
    season = get_effective_season(default_to_current=default_to_current)
    return season.id if season else None
