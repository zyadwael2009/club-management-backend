from flask import Blueprint, request, jsonify, session
from models import db, Match, MatchExpense, GeneralExpense, Player, Club, User
from routes.auth import login_required, admin_or_superadmin_required
from branch_scope import effective_branch_id_for_user
from season_context import get_effective_season_id
from datetime import datetime

matches_bp = Blueprint('matches', __name__)


@matches_bp.route('/', methods=['GET'])
@login_required
def get_matches():
    """Get all matches (filtered by club for admin/coach/player)"""
    current_user = User.query.get(session['user_id'])
    club_id = request.args.get('club_id')
    subgroup_id = request.args.get('subgroup_id')
    season_id = get_effective_season_id(default_to_current=True)
    
    query = Match.query
    branch_id = effective_branch_id_for_user(current_user)
    
    # Role-based filtering
    if current_user.role == 'admin':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'branch_manager':
        query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'coach':
        if current_user.club_id:
            query = query.filter_by(club_id=current_user.club_id)
    elif current_user.role == 'player':
        # Player sees only matches they played in
        if current_user.player_id:
            player = Player.query.get(current_user.player_id)
            if player:
                matches = [m for m in player.matches if (not season_id or m.season_id == season_id)]
                return jsonify([m.to_dict(include_players=True) for m in matches])
        return jsonify([])
    else:
        # Superadmin can filter by club
        if club_id:
            query = query.filter_by(club_id=club_id)
    if branch_id:
        query = query.filter_by(branch_id=branch_id)

    if season_id:
        query = query.filter_by(season_id=season_id)
    
    if subgroup_id:
        query = query.filter_by(subgroup_id=subgroup_id)
    
    matches = query.order_by(Match.match_date.desc()).all()
    return jsonify([m.to_dict(include_players=True) for m in matches])


@matches_bp.route('/<match_id>', methods=['GET'])
@login_required
def get_match(match_id):
    """Get a specific match by ID"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and match.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and match.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'coach' and match.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player':
        # Player can only see matches they played in
        if current_user.player_id:
            player = Player.query.get(current_user.player_id)
            if player and match not in player.matches:
                return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
        else:
            return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    return jsonify(match.to_dict(include_players=True))


@matches_bp.route('/', methods=['POST'])
@admin_or_superadmin_required
def create_match():
    """Create a new match (admin/superadmin only)"""
    current_user = User.query.get(session['user_id'])
    data = request.get_json()
    season_id = get_effective_season_id(default_to_current=True)
    
    if not data.get('clubId'):
        return jsonify({'error': 'معرف النادي مطلوب'}), 400
    
    # Admin can only create matches for their club
    if current_user.role == 'admin' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مباريات لهذا النادي'}), 403
    if current_user.role == 'branch_manager' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مباريات لهذا النادي'}), 403
    branch_id = effective_branch_id_for_user(current_user)
    
    if not data.get('matchType'):
        return jsonify({'error': 'نوع المباراة مطلوب (ودي أو رسمي)'}), 400
    
    if not data.get('opponentName'):
        return jsonify({'error': 'اسم الفريق المنافس مطلوب'}), 400
    
    if not data.get('matchDate'):
        return jsonify({'error': 'تاريخ المباراة مطلوب'}), 400
    
    # Verify club exists
    club = Club.query.get(data['clubId'])
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    match = Match(
        club_id=data['clubId'],
        branch_id=branch_id,
        season_id=season_id,
        match_type=data['matchType'],
        opponent_name=data['opponentName'],
        match_date=datetime.fromisoformat(data['matchDate']).date(),
        our_score=data.get('ourScore'),
        opponent_score=data.get('opponentScore'),
        notes=data.get('notes'),
        subgroup_id=data.get('subgroupId')
    )
    
    # Add players to match
    player_ids = data.get('playerIds', [])
    if player_ids:
        players = Player.query.filter(Player.id.in_(player_ids)).all()
        for player in players:
            match.players.append(player)
    
    db.session.add(match)
    db.session.commit()
    
    return jsonify(match.to_dict(include_players=True)), 201


@matches_bp.route('/<match_id>', methods=['PUT'])
@admin_or_superadmin_required
def update_match(match_id):
    """Update a match (admin/superadmin only)"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only update their club's matches
    if current_user.role == 'admin' and match.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذه المباراة'}), 403
    if current_user.role == 'branch_manager' and match.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذه المباراة'}), 403
    
    data = request.get_json()
    
    if 'matchType' in data:
        match.match_type = data['matchType']
    if 'opponentName' in data:
        match.opponent_name = data['opponentName']
    if 'matchDate' in data:
        match.match_date = datetime.fromisoformat(data['matchDate']).date()
    if 'ourScore' in data:
        match.our_score = data['ourScore']
    if 'opponentScore' in data:
        match.opponent_score = data['opponentScore']
    if 'notes' in data:
        match.notes = data['notes']
    if 'subgroupId' in data:
        match.subgroup_id = data['subgroupId']
    
    # Update players if provided
    if 'playerIds' in data:
        # Clear existing players
        match.players = []
        # Add new players
        player_ids = data['playerIds']
        if player_ids:
            players = Player.query.filter(Player.id.in_(player_ids)).all()
            for player in players:
                match.players.append(player)
    
    db.session.commit()
    return jsonify(match.to_dict(include_players=True))


@matches_bp.route('/<match_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_match(match_id):
    """Delete a match (admin/superadmin only)"""
    match = Match.query.get(match_id)
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only delete their club's matches
    if current_user.role == 'admin' and match.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه المباراة'}), 403
    if current_user.role == 'branch_manager' and match.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه المباراة'}), 403
    
    db.session.delete(match)
    db.session.commit()
    
    return jsonify({'message': 'تم حذف المباراة بنجاح'})


@matches_bp.route('/club/<club_id>', methods=['GET'])
@login_required
def get_club_matches(club_id):
    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'branch_manager' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    """Get all matches for a specific club"""
    club = Club.query.get(club_id)
    if not club:
        return jsonify({'error': 'النادي غير موجود'}), 404
    
    season_id = get_effective_season_id(default_to_current=True)
    query = Match.query.filter_by(club_id=club_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    matches = query.order_by(Match.match_date.desc()).all()
    if current_user.role == 'branch_manager':
        matches = [m for m in matches if m.branch_id == current_user.branch_id]
    return jsonify([m.to_dict(include_players=True) for m in matches])


@matches_bp.route('/player/<player_id>/stats', methods=['GET'])
def get_player_match_stats(player_id):
    """Get match statistics for a specific player"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    return jsonify(player.get_match_stats())


@matches_bp.route('/player/<player_id>', methods=['GET'])
def get_player_matches(player_id):
    """Get all matches a player participated in"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    season_id = get_effective_season_id(default_to_current=True)
    matches_query = player.matches
    if season_id:
        matches_query = matches_query.filter(Match.season_id == season_id)
    matches = matches_query.order_by(Match.match_date.desc()).all()
    return jsonify([m.to_dict() for m in matches])


@matches_bp.route('/expenses/club/<club_id>', methods=['GET'])
@login_required
def get_club_match_expenses(club_id):
    """Get all match expenses for a club."""
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
    query = MatchExpense.query.filter_by(club_id=club_id)
    if current_user.role == 'branch_manager':
        query = query.filter_by(branch_id=current_user.branch_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    expenses = query.order_by(MatchExpense.payment_date.desc()).all()
    return jsonify([e.to_dict() for e in expenses]), 200


@matches_bp.route('/expenses', methods=['POST'])
@admin_or_superadmin_required
def create_match_expense():
    """Create a new expense record for a specific match."""
    current_user = User.query.get(session['user_id'])
    data = request.get_json() or {}

    required = ['matchId', 'expenseType', 'amount', 'paymentDate']
    if any(not data.get(field) for field in required):
        return jsonify({'error': 'بيانات المصروف غير مكتملة'}), 400

    match = Match.query.get(data['matchId'])
    if not match:
        return jsonify({'error': 'المباراة غير موجودة'}), 404

    if current_user.role == 'admin' and match.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مصروف لهذه المباراة'}), 403
    if current_user.role == 'branch_manager' and match.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مصروف لهذه المباراة'}), 403

    allowed_types = {'transportation', 'ambulance', 'field_rent'}
    if data['expenseType'] not in allowed_types:
        return jsonify({'error': 'نوع المصروف غير مدعوم'}), 400

    try:
        amount = float(data['amount'])
        if amount <= 0:
            return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

        expense = MatchExpense(
            club_id=match.club_id,
            branch_id=match.branch_id,
            match_id=match.id,
            season_id=match.season_id,
            expense_type=data['expenseType'],
            expense_scope=data.get('expenseScope', 'club'),
            amount=amount,
            payment_date=datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date(),
            notes=data.get('notes'),
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(expense.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إضافة مصروف المباراة: {str(e)}'}), 500


@matches_bp.route('/expenses/<expense_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_match_expense(expense_id):
    """Delete a match expense record."""
    current_user = User.query.get(session['user_id'])
    expense = MatchExpense.query.get(expense_id)
    if not expense:
        return jsonify({'error': 'المصروف غير موجود'}), 404

    if current_user.role == 'admin' and expense.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المصروف'}), 403
    if current_user.role == 'branch_manager' and expense.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المصروف'}), 403

    try:
        db.session.delete(expense)
        db.session.commit()
        return jsonify({'message': 'تم حذف المصروف بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف المصروف: {str(e)}'}), 500


@matches_bp.route('/general-expenses/club/<club_id>', methods=['GET'])
@login_required
def get_club_general_expenses(club_id):
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
    query = GeneralExpense.query.filter_by(club_id=club_id)
    if current_user.role == 'branch_manager':
        query = query.filter_by(branch_id=current_user.branch_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    expenses = query.order_by(GeneralExpense.payment_date.desc()).all()
    return jsonify([e.to_dict() for e in expenses]), 200


@matches_bp.route('/general-expenses', methods=['POST'])
@admin_or_superadmin_required
def create_general_expense():
    current_user = User.query.get(session['user_id'])
    data = request.get_json() or {}

    required = ['clubId', 'expenseType', 'expenseScope', 'amount', 'paymentDate']
    if any(not data.get(field) for field in required):
        return jsonify({'error': 'بيانات المصروف غير مكتملة'}), 400

    if current_user.role == 'admin' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مصروف لهذا النادي'}), 403
    if current_user.role == 'branch_manager' and data['clubId'] != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة مصروف لهذا النادي'}), 403
    branch_id = effective_branch_id_for_user(current_user)

    if data['expenseType'] not in ['training_field_rent', 'clothing']:
        return jsonify({'error': 'نوع المصروف غير مدعوم'}), 400
    if data['expenseScope'] not in ['club', 'academy']:
        return jsonify({'error': 'النطاق يجب أن يكون club أو academy'}), 400

    try:
        season_id = get_effective_season_id(default_to_current=True)
        amount = float(data['amount'])
        if amount <= 0:
            return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

        budget_amount = data.get('budgetAmount')
        if budget_amount is not None:
            budget_amount = float(budget_amount)
            if budget_amount < 0:
                return jsonify({'error': 'الميزانية يجب أن تكون أكبر من أو تساوي صفر'}), 400

        expense = GeneralExpense(
            club_id=data['clubId'],
            branch_id=branch_id,
            season_id=season_id,
            expense_type=data['expenseType'],
            expense_scope=data['expenseScope'],
            amount=amount,
            budget_amount=budget_amount,
            payment_date=datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date(),
            notes=data.get('notes'),
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify(expense.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إضافة المصروف العام: {str(e)}'}), 500


@matches_bp.route('/general-expenses/<expense_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_general_expense(expense_id):
    current_user = User.query.get(session['user_id'])
    expense = GeneralExpense.query.get(expense_id)
    if not expense:
        return jsonify({'error': 'المصروف غير موجود'}), 404

    if current_user.role == 'admin' and expense.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المصروف'}), 403
    if current_user.role == 'branch_manager' and expense.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذا المصروف'}), 403

    try:
        db.session.delete(expense)
        db.session.commit()
        return jsonify({'message': 'تم حذف المصروف بنجاح'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف المصروف: {str(e)}'}), 500
