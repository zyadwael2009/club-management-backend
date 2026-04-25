from flask import Blueprint, request, jsonify, session
from models import db, Player, PlayerPayment, User
from routes.auth import login_required, admin_or_superadmin_required
from season_context import get_effective_season_id
from datetime import datetime, date
import calendar

player_payments = Blueprint('player_payments', __name__)


def _add_one_month_keep_day(base_date, day_of_month):
    year = base_date.year
    month = base_date.month + 1
    if month > 12:
        month = 1
        year += 1
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, max_day))


def _apply_player_renewals(player, today=None):
    # Renewal is now managed by explicit subscription dates, not auto day-of-month rolling.
    return False


def _reset_subscription_after_full_payment(player, paid_date):
    if not player.monthly_amount or player.monthly_amount <= 0:
        return
    if player.amount_due is None or player.amount_due > 0:
        return

    start_date = paid_date
    end_date = _add_one_month_keep_day(start_date, start_date.day)
    player.subscription_start_date = start_date
    player.subscription_end_date = end_date


def _ensure_league_due_initialized(player):
    if player.league_due is not None:
        normalized = max(0.0, float(player.league_due or 0.0))
        if normalized != float(player.league_due or 0.0):
            player.league_due = normalized
        return normalized

    total_due = max(0.0, float(player.amount_due or 0.0))
    monthly_due_component = max(0.0, float(player.monthly_amount or 0.0))
    inferred_league_due = max(0.0, total_due - monthly_due_component) if monthly_due_component > 0 else total_due
    player.league_due = inferred_league_due
    return inferred_league_due


def _compute_due_buckets(player):
    total_due = max(0.0, float(player.amount_due or 0.0))
    league_due = max(0.0, float(_ensure_league_due_initialized(player) or 0.0))
    if league_due > total_due:
        league_due = total_due
    monthly_due = max(0.0, total_due - league_due)
    return total_due, monthly_due, league_due


def _initialize_club_monthly_subscription(player):
    subgroup_monthly = float(player.subgroup.monthly_amount or 0.0) if player.subgroup else 0.0
    club_monthly = float(player.club.monthly_amount or 0.0) if player.club else 0.0
    resolved_monthly = subgroup_monthly if subgroup_monthly > 0 else club_monthly
    if resolved_monthly <= 0:
        raise ValueError('المبلغ الشهري غير مُعد. قم بتحديده في المجموعة أو إعدادات النادي أولاً')

    existing_league_due = _ensure_league_due_initialized(player)
    subgroup_league_default = float(player.subgroup.league_amount or 0.0) if player.subgroup else 0.0
    if existing_league_due <= 0 and subgroup_league_default > 0:
        player.league_due = subgroup_league_default
        existing_league_due = subgroup_league_default

    player.monthly_amount = resolved_monthly
    if player.amount_due is None or float(player.amount_due) <= 0:
        player.amount_due = resolved_monthly + existing_league_due

    if player.subscription_start_date is None:
        base = date.today()
        player.subscription_start_date = base
        player.subscription_end_date = _add_one_month_keep_day(base, base.day)


def _apply_payment_delta_by_type(player, payment_type, amount, is_revert=False):
    """Apply or revert payment effect by bucket type.

    - monthly_subscription affects only monthly due bucket.
    - league_subscription affects only league due bucket.
    """
    normalized_type = _normalized_payment_type(player, payment_type)
    if normalized_type not in ['monthly_subscription', 'league_subscription']:
        return 0.0

    total_due, monthly_due, league_due = _compute_due_buckets(player)
    delta = max(0.0, float(amount or 0.0))
    applied = 0.0

    if is_revert:
        if normalized_type == 'league_subscription':
            league_due += delta
            total_due += delta
            applied = delta
        else:
            total_due += delta
            applied = delta
    else:
        if normalized_type == 'league_subscription':
            applied = min(delta, league_due)
            league_due = max(0.0, league_due - applied)
            total_due = max(0.0, total_due - applied)
        else:
            applied = min(delta, monthly_due)
            total_due = max(0.0, total_due - applied)

    if league_due > total_due:
        league_due = total_due

    player.league_due = league_due
    player.amount_due = total_due
    player.payment_status = 'paid' if total_due <= 0 else 'unpaid'
    return applied


def _normalized_payment_type(player, payment_type):
    if payment_type in ['league_subscription', 'monthly_subscription', 'clothing_bag']:
        return payment_type

    subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
    has_monthly_subscription = float(player.monthly_amount or 0.0) > 0
    if subgroup_type == 'academy' and has_monthly_subscription:
        return 'monthly_subscription'
    return 'league_subscription'


def _should_payment_affect_due(player, payment_type):
    normalized = _normalized_payment_type(player, payment_type)
    # Only subscription payments contribute to settling outstanding due.
    return normalized in ['monthly_subscription', 'league_subscription']


def _resolve_payment_type_for_player(player, raw_payment_type, existing_payment_type=None):
    allowed_types = ['league_subscription', 'monthly_subscription', 'clothing_bag']
    payment_type = raw_payment_type if raw_payment_type in allowed_types else _normalized_payment_type(player, raw_payment_type)

    if payment_type == 'monthly_subscription':
        subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
        if subgroup_type == 'club':
            _initialize_club_monthly_subscription(player)
        else:
            has_monthly_subscription = float(player.monthly_amount or 0.0) > 0
            is_existing_monthly = existing_payment_type == 'monthly_subscription'
            if not has_monthly_subscription and not is_existing_monthly:
                raise ValueError('لا يمكن تسجيل اشتراك شهري لهذا اللاعب لأن الاشتراك الشهري غير مفعل')

    return payment_type


@player_payments.route('/<player_id>/payments', methods=['GET'])
@login_required
def get_player_payments(player_id):
    """Get payment history for a player"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player' and current_user.player_id != player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    season_id = get_effective_season_id(default_to_current=True)
    query = PlayerPayment.query.filter_by(player_id=player_id)
    if season_id:
        query = query.filter_by(season_id=season_id)
    payments = query.order_by(PlayerPayment.payment_date.desc()).all()
    return jsonify([payment.to_dict() for payment in payments]), 200


@player_payments.route('/club/<club_id>/payments', methods=['GET'])
@login_required
def get_club_player_payments(club_id):
    """Get all player payments for a club (used as revenues)."""
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
        db.session.query(PlayerPayment, Player)
        .join(Player, PlayerPayment.player_id == Player.id)
        .filter(Player.club_id == club_id)
        .filter(PlayerPayment.season_id == season_id if season_id else True)
        .order_by(PlayerPayment.payment_date.desc())
        .all()
    )
    if current_user.role == 'branch_manager':
        rows = [(payment, player) for payment, player in rows if payment.branch_id == current_user.branch_id]

    result = []
    for payment, player in rows:
        item = payment.to_dict()
        item['playerName'] = player.full_name
        item['clubId'] = player.club_id
        item['playerSubgroupType'] = player.subgroup.subgroup_type if player.subgroup else 'club'
        item['playerSubgroupName'] = player.subgroup.name if player.subgroup else None
        item['playerMonthlyAmount'] = float(player.monthly_amount or 0.0)
        item['playerLeagueDue'] = float(player.league_due or 0.0)
        result.append(item)

    return jsonify(result), 200


@player_payments.route('/<player_id>/payments', methods=['POST'])
@admin_or_superadmin_required
def add_player_payment(player_id):
    """Record a payment received from a player"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    if not bool(player.is_active):
        return jsonify({'error': 'لا يمكن إضافة دفعة للاعب غير نشط'}), 400
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only add payments for their club's players
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة دفعات لهذا اللاعب'}), 403
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لإضافة دفعات لهذا اللاعب'}), 403
    
    data = request.json
    
    if not data.get('amountPaid') or not data.get('paymentDate'):
        return jsonify({'error': 'المبلغ وتاريخ الدفع مطلوبان'}), 400
    
    try:
        amount_paid = float(data['amountPaid'])
        if amount_paid <= 0:
            return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

        payment_date = datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date()

        _apply_player_renewals(player)
        season_id = get_effective_season_id(default_to_current=True)

        subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
        forced_scope = 'academy' if subgroup_type == 'academy' else 'club'

        requested_scope = data.get('revenueScope', forced_scope)
        revenue_scope = forced_scope
        if requested_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع الإيراد يجب أن يكون club أو academy'}), 400

        payment_type = data.get('paymentType')
        payment_type = _resolve_payment_type_for_player(player, payment_type)

        total_due, monthly_due, league_due = _compute_due_buckets(player)
        if payment_type == 'monthly_subscription' and amount_paid > monthly_due:
            return jsonify({'error': 'المبلغ يتجاوز المتبقي من الاشتراك الشهري'}), 400
        if payment_type == 'league_subscription' and amount_paid > league_due:
            return jsonify({'error': 'المبلغ يتجاوز المتبقي من اشتراك الدوري'}), 400

        if payment_type == 'monthly_subscription':
            month_key = payment_date.strftime('%Y-%m')
            same_month_entries_count = (
                PlayerPayment.query
                .filter_by(player_id=player_id)
                .filter(PlayerPayment.season_id == season_id if season_id else True)
                .filter(PlayerPayment.payment_type == 'monthly_subscription')
                .filter(db.extract('year', PlayerPayment.payment_date) == payment_date.year)
                .filter(db.extract('month', PlayerPayment.payment_date) == payment_date.month)
                .count()
            )
            if same_month_entries_count > 0:
                return jsonify({
                    'error': f'تم تسجيل اشتراك شهري بالفعل في شهر {month_key}'
                }), 400

            # Block creating a new monthly subscription payment while current period is still active.
            if player.subscription_end_date is not None and payment_date <= player.subscription_end_date and monthly_due <= 0:
                return jsonify({
                    'error': 'لا يمكن إضافة اشتراك شهري جديد قبل انتهاء فترة الاشتراك الحالية'
                }), 400

        payment = PlayerPayment(
            player_id=player_id,
            branch_id=player.branch_id,
            season_id=season_id,
            amount_paid=amount_paid,
            revenue_scope=revenue_scope,
            payment_type=payment_type,
            payment_date=payment_date,
            notes=data.get('notes')
        )

        # Keep player due amount in sync with recorded payments.
        if _should_payment_affect_due(player, payment_type):
            _apply_payment_delta_by_type(player, payment_type, amount_paid, is_revert=False)
        _reset_subscription_after_full_payment(player, payment.payment_date)

        db.session.add(payment)
        db.session.commit()
        
        return jsonify(payment.to_dict()), 201
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل إضافة الدفعة: {str(e)}'}), 500


@player_payments.route('/<player_id>/payments/<payment_id>', methods=['DELETE'])
@admin_or_superadmin_required
def delete_player_payment(player_id, payment_id):
    """Delete a player payment record"""
    payment = PlayerPayment.query.get(payment_id)
    if not payment or payment.player_id != player_id:
        return jsonify({'error': 'الدفعة غير موجودة'}), 404
    
    player = Player.query.get(player_id)
    current_user = User.query.get(session['user_id'])
    
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه الدفعة'}), 403
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لحذف هذه الدفعة'}), 403
    
    try:
        _apply_player_renewals(player)

        # Revert due amount when deleting a payment to preserve consistency.
        if _should_payment_affect_due(player, payment.payment_type):
            _apply_payment_delta_by_type(player, payment.payment_type, payment.amount_paid, is_revert=True)

        db.session.delete(payment)
        db.session.commit()
        return jsonify({'message': 'تم حذف الدفعة بنجاح'}), 200
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل حذف الدفعة: {str(e)}'}), 500


@player_payments.route('/<player_id>/payments/summary', methods=['GET'])
@login_required
def get_player_payment_summary(player_id):
    """Get payment summary for a player (total paid, outstanding balance)"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Check permissions
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    elif current_user.role == 'player' and current_user.player_id != player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    season_id = get_effective_season_id(default_to_current=True)

    if _apply_player_renewals(player):
        db.session.commit()

    # Calculate total paid and typed totals.
    payments_query = PlayerPayment.query.filter_by(player_id=player_id)
    if season_id:
        payments_query = payments_query.filter_by(season_id=season_id)
    payments = payments_query.all()
    total_paid = sum(payment.amount_paid for payment in payments)

    monthly_total = 0.0
    league_total = 0.0
    monthly_payment_count = 0
    academy_monthly_count = 0
    for payment in payments:
        payment_type = payment.payment_type
        if payment_type is None:
            payment_type = 'monthly_subscription' if payment.revenue_scope == 'academy' else 'league_subscription'

        if payment_type == 'monthly_subscription':
            monthly_total += float(payment.amount_paid or 0.0)
            monthly_payment_count += 1
            if payment.revenue_scope == 'academy':
                academy_monthly_count += 1
        elif payment_type == 'league_subscription':
            league_total += float(payment.amount_paid or 0.0)
    
    current_month = date.today()
    current_month_monthly_total = 0.0
    current_month_paid = False
    for payment in payments:
        if payment.payment_type != 'monthly_subscription':
            continue
        if payment.payment_date and payment.payment_date.year == current_month.year and payment.payment_date.month == current_month.month:
            current_month_monthly_total += float(payment.amount_paid or 0.0)
            current_month_paid = True

    # amount_due is stored as the remaining balance in player profile.
    if bool(player.is_active):
        amount_due = max(0.0, float(player.amount_due or 0.0))
        league_outstanding = max(0.0, float(player.league_due or 0.0))
    else:
        amount_due = 0.0
        league_outstanding = 0.0
    if league_outstanding > amount_due:
        league_outstanding = amount_due
    monthly_outstanding = max(0.0, amount_due - league_outstanding)
    outstanding_balance = amount_due
    
    return jsonify({
        'totalPaid': total_paid,
        'monthlySubscriptionTotal': monthly_total,
        'leagueSubscriptionTotal': league_total,
        'monthlyPaymentCount': monthly_payment_count,
        'academyMonthlyPaymentCount': academy_monthly_count,
        'amountDue': amount_due,
        'monthlyOutstandingDue': monthly_outstanding,
        'leagueOutstandingDue': league_outstanding,
        'outstandingBalance': outstanding_balance,
        'paymentCount': len(payments),
        'seasonId': season_id,
        'isActive': bool(player.is_active),
        'currentMonth': current_month.strftime('%Y-%m'),
        'currentMonthMonthlySubscriptionTotal': current_month_monthly_total,
        'hasCurrentMonthMonthlyPayment': current_month_paid,
    }), 200


@player_payments.route('/<player_id>/payments/<payment_id>', methods=['PUT'])
@admin_or_superadmin_required
def update_player_payment(player_id, payment_id):
    """Edit an existing player payment and keep due amount in sync."""
    payment = PlayerPayment.query.get(payment_id)
    if not payment or payment.player_id != player_id:
        return jsonify({'error': 'الدفعة غير موجودة'}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    if not bool(player.is_active):
        return jsonify({'error': 'لا يمكن تعديل دفعات لاعب غير نشط'}), 400

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذه الدفعة'}), 403
    if current_user.role == 'branch_manager' and player.branch_id != current_user.branch_id:
        return jsonify({'error': 'ليس لديك صلاحية لتعديل هذه الدفعة'}), 403

    data = request.json or {}

    if data.get('amountPaid') is None or not data.get('paymentDate'):
        return jsonify({'error': 'المبلغ وتاريخ الدفع مطلوبان'}), 400

    try:
        new_amount = float(data['amountPaid'])
        if new_amount <= 0:
            return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400

        subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
        forced_scope = 'academy' if subgroup_type == 'academy' else 'club'

        requested_scope = data.get('revenueScope', payment.revenue_scope or forced_scope)
        revenue_scope = forced_scope
        if requested_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع الإيراد يجب أن يكون club أو academy'}), 400

        new_payment_type = data.get('paymentType', payment.payment_type)
        new_payment_type = _resolve_payment_type_for_player(
            player,
            new_payment_type,
            existing_payment_type=payment.payment_type,
        )

        _apply_player_renewals(player)
        new_payment_date = datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date()

        if new_payment_type == 'monthly_subscription':
            same_month_exists = (
                PlayerPayment.query
                .filter_by(player_id=player_id)
                .filter(PlayerPayment.id != payment.id)
                .filter(PlayerPayment.season_id == payment.season_id if payment.season_id else True)
                .filter(PlayerPayment.payment_type == 'monthly_subscription')
                .filter(db.extract('year', PlayerPayment.payment_date) == new_payment_date.year)
                .filter(db.extract('month', PlayerPayment.payment_date) == new_payment_date.month)
                .count()
            )
            if same_month_exists > 0:
                return jsonify({'error': f'يوجد اشتراك شهري آخر مسجل في {new_payment_date.strftime("%Y-%m")}'}), 400

        old_amount = float(payment.amount_paid)
        old_payment_type = payment.payment_type

        simulated_total_due, simulated_monthly_due, simulated_league_due = _compute_due_buckets(player)
        normalized_old_type = _normalized_payment_type(player, old_payment_type)
        if normalized_old_type == 'league_subscription':
            simulated_total_due += old_amount
            simulated_league_due += old_amount
        elif normalized_old_type == 'monthly_subscription':
            simulated_total_due += old_amount

        if simulated_league_due > simulated_total_due:
            simulated_league_due = simulated_total_due
        simulated_monthly_due = max(0.0, simulated_total_due - simulated_league_due)

        if new_payment_type == 'league_subscription' and new_amount > simulated_league_due:
            return jsonify({'error': 'المبلغ يتجاوز المتبقي من اشتراك الدوري'}), 400
        if new_payment_type == 'monthly_subscription' and new_amount > simulated_monthly_due:
            return jsonify({'error': 'المبلغ يتجاوز المتبقي من الاشتراك الشهري'}), 400

        payment.amount_paid = new_amount
        payment.revenue_scope = revenue_scope
        payment.payment_type = new_payment_type
        payment.payment_date = new_payment_date
        payment.notes = data.get('notes')

        # Undo old payment effect then apply updated one.
        old_affects_due = _should_payment_affect_due(player, old_payment_type)
        new_affects_due = _should_payment_affect_due(player, new_payment_type)
        if old_affects_due:
            _apply_payment_delta_by_type(player, old_payment_type, old_amount, is_revert=True)
        if new_affects_due:
            _apply_payment_delta_by_type(player, new_payment_type, new_amount, is_revert=False)
        _reset_subscription_after_full_payment(player, payment.payment_date)

        db.session.commit()
        return jsonify(payment.to_dict()), 200

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل تعديل الدفعة: {str(e)}'}), 500
