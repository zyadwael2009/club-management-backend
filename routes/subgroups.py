from flask import Blueprint, request, jsonify, session
from sqlalchemy import func, and_, or_
from models import db, Subgroup, Club, User, Player, PlayerPayment
from routes.auth import login_required, admin_or_superadmin_required, ensure_coach_permission
from branch_scope import effective_branch_id_for_user, resolve_creation_branch_for_user
from season_context import get_effective_season_id

subgroups_bp = Blueprint('subgroups', __name__)


def _get_player_league_revenue_totals(player_ids, season_id=None):
    """Return league subscription revenues grouped by player for the active scope."""
    if not player_ids:
        return {}

    query = (
        db.session.query(
            PlayerPayment.player_id,
            func.coalesce(func.sum(PlayerPayment.amount_paid), 0.0),
        )
        .filter(PlayerPayment.player_id.in_(player_ids))
        .filter(
            or_(
                PlayerPayment.payment_type == 'league_subscription',
                and_(
                    PlayerPayment.payment_type.is_(None),
                    PlayerPayment.revenue_scope != 'academy',
                ),
            )
        )
    )

    if season_id:
        query = query.filter(PlayerPayment.season_id == season_id)

    rows = query.group_by(PlayerPayment.player_id).all()
    return {player_id: float(total or 0.0) for player_id, total in rows}


@subgroups_bp.route('/', methods=['GET'])
@login_required
def get_subgroups():
    """Get all subgroups (filtered by club for admin/coach)"""
    current_user = User.query.get(session['user_id'])

    permission_error = ensure_coach_permission(current_user, 'subgroups')
    if permission_error:
        return permission_error
    club_id = request.args.get('club_id')
    
    query = Subgroup.query
    branch_id = effective_branch_id_for_user(current_user)
    
    # Role-based filtering
    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
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
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    
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

    permission_error = ensure_coach_permission(current_user, 'subgroups')
    if permission_error:
        return permission_error
    
    # Check permissions
    if current_user.role == 'admin' and subgroup.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and subgroup.branch_id != current_user.branch_id:
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
    if current_user.role == 'branch_manager' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مجموعات لهذا النادي'}), 403
    branch_id, branch_error = resolve_creation_branch_for_user(current_user, data['clubId'])
    if branch_error:
        return jsonify({'error': branch_error}), 400
    
    if not data.get('subgroupType'):
        return jsonify({'error': 'نوع المجموعة مطلوب (أكاديمية أو نادي)'}), 400
    
    if data.get('birthYear') is None:
        return jsonify({'error': 'سنة الميلاد مطلوبة'}), 400

    monthly_amount = data.get('monthlyAmount')
    if monthly_amount not in [None, '']:
        try:
            monthly_amount = float(monthly_amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'المبلغ الشهري غير صالح'}), 400
        if monthly_amount <= 0:
            return jsonify({'error': 'المبلغ الشهري يجب أن يكون أكبر من صفر'}), 400
    else:
        monthly_amount = None

    league_amount = data.get('leagueAmount')
    if league_amount not in [None, '']:
        try:
            league_amount = float(league_amount)
        except (TypeError, ValueError):
            return jsonify({'error': 'مبلغ اشتراك الدوري غير صالح'}), 400
        if league_amount < 0:
            return jsonify({'error': 'مبلغ اشتراك الدوري لا يمكن أن يكون أقل من صفر'}), 400
    else:
        league_amount = None

    if data.get('subgroupType') == 'academy' and monthly_amount is None:
        return jsonify({'error': 'المبلغ الشهري مطلوب لمجموعة الأكاديمية'}), 400
    
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
        branch_id=branch_id,
        subgroup_type=data['subgroupType'],
        birth_year=birth_year,
        monthly_amount=monthly_amount,
        league_amount=league_amount,
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
    if current_user.role == 'branch_manager' and subgroup.branch_id != current_user.branch_id:
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

    if 'monthlyAmount' in data:
        if data['monthlyAmount'] in ['', None]:
            subgroup.monthly_amount = None
        else:
            try:
                subgroup.monthly_amount = float(data['monthlyAmount'])
            except (TypeError, ValueError):
                return jsonify({'error': 'المبلغ الشهري غير صالح'}), 400
            if subgroup.monthly_amount <= 0:
                return jsonify({'error': 'المبلغ الشهري يجب أن يكون أكبر من صفر'}), 400

    league_amount_updated = False
    if 'leagueAmount' in data:
        league_amount_updated = True
        if data['leagueAmount'] in ['', None]:
            subgroup.league_amount = None
        else:
            try:
                subgroup.league_amount = float(data['leagueAmount'])
            except (TypeError, ValueError):
                return jsonify({'error': 'مبلغ اشتراك الدوري غير صالح'}), 400
            if subgroup.league_amount < 0:
                return jsonify({'error': 'مبلغ اشتراك الدوري لا يمكن أن يكون أقل من صفر'}), 400

    if subgroup.subgroup_type == 'academy' and (subgroup.monthly_amount is None or subgroup.monthly_amount <= 0):
        return jsonify({'error': 'المبلغ الشهري مطلوب لمجموعة الأكاديمية'}), 400

    # Keep players in subgroup aligned with subgroup monthly amount.
    if subgroup.subgroup_type == 'academy' and subgroup.monthly_amount is not None:
        players = Player.query.filter_by(subgroup_id=subgroup.id).all()
        for player in players:
            player.monthly_amount = subgroup.monthly_amount

    if league_amount_updated:
        players = Player.query.filter_by(subgroup_id=subgroup.id).all()
        season_id = get_effective_season_id(default_to_current=True)
        league_total = max(0.0, float(subgroup.league_amount or 0.0))
        league_paid_by_player = _get_player_league_revenue_totals(
            [player.id for player in players],
            season_id=season_id,
        )

        for player in players:
            current_total_due = max(0.0, float(player.amount_due or 0.0))
            current_league_due = max(0.0, float(player.league_due or 0.0))
            if current_league_due > current_total_due:
                current_league_due = current_total_due

            monthly_outstanding_due = max(0.0, current_total_due - current_league_due)
            paid_league_revenue = max(0.0, float(league_paid_by_player.get(player.id, 0.0)))
            remaining_league_due = max(0.0, league_total - paid_league_revenue)

            player.league_due = remaining_league_due
            player.amount_due = monthly_outstanding_due + remaining_league_due
            player.payment_status = 'paid' if float(player.amount_due or 0.0) <= 0 else 'unpaid'
    
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
    if current_user.role == 'branch_manager' and subgroup.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه المجموعة'}), 403
    
    db.session.delete(subgroup)
    db.session.commit()
    
    return jsonify({'message': 'تم حذف المجموعة الفرعية بنجاح'})


@subgroups_bp.route('/club/<club_id>', methods=['GET'])
@login_required
def get_club_subgroups(club_id):
    """Get all subgroups for a specific club"""
    club = Club.query.get(club_id)
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role not in ['superadmin', 'admin', 'branch_manager', 'coach']:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    query = Subgroup.query.filter_by(club_id=club_id)
    branch_id = effective_branch_id_for_user(current_user)
    if branch_id:
        query = query.filter_by(branch_id=branch_id)
    subgroups = query.order_by(Subgroup.birth_year.desc()).all()
    return jsonify([sg.to_dict() for sg in subgroups])
