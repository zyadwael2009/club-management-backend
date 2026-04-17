from flask import Blueprint, request, jsonify, session
from models import db, Player, PlayerPayment, User
from routes.auth import login_required, admin_or_superadmin_required
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


def _initialize_club_monthly_subscription(player):
    subgroup_monthly = float(player.subgroup.monthly_amount or 0.0) if player.subgroup else 0.0
    club_monthly = float(player.club.monthly_amount or 0.0) if player.club else 0.0
    resolved_monthly = subgroup_monthly if subgroup_monthly > 0 else club_monthly
    if resolved_monthly <= 0:
        raise ValueError('المبلغ الشهري غير مُعد. قم بتحديده في المجموعة أو إعدادات النادي أولاً')

    player.monthly_amount = resolved_monthly
    if player.amount_due is None or float(player.amount_due) <= 0:
        player.amount_due = resolved_monthly

    if player.subscription_start_date is None:
        base = date.today()
        player.subscription_start_date = base
        player.subscription_end_date = _add_one_month_keep_day(base, base.day)


def _recompute_due_after_payment_change(player, delta_revert=0.0, delta_apply=0.0):
    """Recompute player's due amount and payment status safely.

    delta_revert: amount to add back to due (when removing old payment effect)
    delta_apply: amount to subtract from due (when applying new payment effect)
    """
    had_due_before = player.amount_due is not None
    current_due = float(player.amount_due) if had_due_before else 0.0
    new_due = max(0.0, (current_due + float(delta_revert)) - float(delta_apply))

    player.amount_due = new_due
    if had_due_before or (player.monthly_amount is not None and player.monthly_amount > 0):
        player.payment_status = 'paid' if new_due <= 0 else 'unpaid'
    # If due tracking was previously uninitialized, keep the existing status unchanged.


def _normalized_payment_type(player, payment_type):
    if payment_type in ['league_subscription', 'monthly_subscription', 'clothing_bag']:
        return payment_type
    subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
    return 'monthly_subscription' if subgroup_type == 'academy' else 'league_subscription'


def _should_payment_affect_due(player, payment_type):
    normalized = _normalized_payment_type(player, payment_type)
    # Only subscription payments contribute to settling outstanding due.
    return normalized in ['monthly_subscription', 'league_subscription']


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
    elif current_user.role == 'player' and current_user.player_id != player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    payments = PlayerPayment.query.filter_by(player_id=player_id).order_by(PlayerPayment.payment_date.desc()).all()
    return jsonify([payment.to_dict() for payment in payments]), 200


@player_payments.route('/club/<club_id>/payments', methods=['GET'])
@login_required
def get_club_player_payments(club_id):
    """Get all player payments for a club (used as revenues)."""
    current_user = User.query.get(session['user_id'])

    if current_user.role == 'admin' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'coach' and current_user.club_id != club_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    if current_user.role == 'player':
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403

    rows = (
        db.session.query(PlayerPayment, Player)
        .join(Player, PlayerPayment.player_id == Player.id)
        .filter(Player.club_id == club_id)
        .order_by(PlayerPayment.payment_date.desc())
        .all()
    )

    result = []
    for payment, player in rows:
        item = payment.to_dict()
        item['playerName'] = player.full_name
        item['clubId'] = player.club_id
        item['playerSubgroupType'] = player.subgroup.subgroup_type if player.subgroup else 'club'
        item['playerSubgroupName'] = player.subgroup.name if player.subgroup else None
        result.append(item)

    return jsonify(result), 200


@player_payments.route('/<player_id>/payments', methods=['POST'])
@admin_or_superadmin_required
def add_player_payment(player_id):
    """Record a payment received from a player"""
    player = Player.query.get(player_id)
    if not player:
        return jsonify({'error': 'اللاعب غير موجود'}), 404
    
    current_user = User.query.get(session['user_id'])
    
    # Admin can only add payments for their club's players
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
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

        subgroup_type = (player.subgroup.subgroup_type if player.subgroup else 'club') or 'club'
        forced_scope = 'academy' if subgroup_type == 'academy' else 'club'

        requested_scope = data.get('revenueScope', forced_scope)
        revenue_scope = forced_scope
        if requested_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع الإيراد يجب أن يكون club أو academy'}), 400

        payment_type = data.get('paymentType')
        if subgroup_type == 'club':
            if payment_type not in ['league_subscription', 'monthly_subscription', 'clothing_bag']:
                payment_type = 'league_subscription'
            if payment_type == 'monthly_subscription':
                _initialize_club_monthly_subscription(player)
        else:
            payment_type = 'monthly_subscription'

        if payment_type == 'monthly_subscription':
            monthly_entries_count = (
                PlayerPayment.query
                .filter_by(player_id=player_id)
                .filter(PlayerPayment.payment_type == 'monthly_subscription')
                .count()
            )
            current_due = float(player.amount_due or 0.0)
            if monthly_entries_count > 0 and current_due > 0:
                return jsonify({
                    'error': 'لا يمكن إضافة اشتراك شهري جديد قبل تسوية المستحق الحالي. عدّل الإيراد السابق ليطابق القسط الشهري'
                }), 400

            # Block creating a new monthly subscription payment while current period is still active.
            if player.subscription_end_date is not None and payment_date <= player.subscription_end_date and current_due <= 0:
                return jsonify({
                    'error': 'لا يمكن إضافة اشتراك شهري جديد قبل انتهاء فترة الاشتراك الحالية'
                }), 400

        payment = PlayerPayment(
            player_id=player_id,
            amount_paid=amount_paid,
            revenue_scope=revenue_scope,
            payment_type=payment_type,
            payment_date=payment_date,
            notes=data.get('notes')
        )

        # Keep player due amount in sync with recorded payments.
        if _should_payment_affect_due(player, payment_type):
            _recompute_due_after_payment_change(player, delta_revert=0.0, delta_apply=amount_paid)
        _reset_subscription_after_full_payment(player, payment.payment_date)

        db.session.add(payment)
        db.session.commit()
        
        return jsonify(payment.to_dict()), 201
    
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
    
    try:
        _apply_player_renewals(player)

        # Revert due amount when deleting a payment to preserve consistency.
        if _should_payment_affect_due(player, payment.payment_type):
            _recompute_due_after_payment_change(player, delta_revert=payment.amount_paid, delta_apply=0.0)

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
    elif current_user.role == 'player' and current_user.player_id != player_id:
        return jsonify({'error': 'ليس لديك صلاحية للوصول'}), 403
    
    if _apply_player_renewals(player):
        db.session.commit()

    # Calculate total paid and typed totals.
    payments = PlayerPayment.query.filter_by(player_id=player_id).all()
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
    
    # amount_due is stored as the remaining balance in player profile.
    amount_due = player.amount_due or 0
    outstanding_balance = max(0.0, amount_due)
    
    return jsonify({
        'totalPaid': total_paid,
        'monthlySubscriptionTotal': monthly_total,
        'leagueSubscriptionTotal': league_total,
        'monthlyPaymentCount': monthly_payment_count,
        'academyMonthlyPaymentCount': academy_monthly_count,
        'amountDue': amount_due,
        'outstandingBalance': outstanding_balance,
        'paymentCount': len(payments)
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

    current_user = User.query.get(session['user_id'])
    if current_user.role == 'admin' and player.club_id != current_user.club_id:
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
        if subgroup_type == 'club':
            if new_payment_type not in ['league_subscription', 'monthly_subscription', 'clothing_bag']:
                new_payment_type = 'league_subscription'
            if new_payment_type == 'monthly_subscription':
                _initialize_club_monthly_subscription(player)
        else:
            new_payment_type = 'monthly_subscription'

        _apply_player_renewals(player)

        old_amount = float(payment.amount_paid)
        old_payment_type = payment.payment_type
        payment.amount_paid = new_amount
        payment.revenue_scope = revenue_scope
        payment.payment_type = new_payment_type
        payment.payment_date = datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date()
        payment.notes = data.get('notes')

        # Undo old payment effect then apply updated one.
        old_affects_due = _should_payment_affect_due(player, old_payment_type)
        new_affects_due = _should_payment_affect_due(player, new_payment_type)
        _recompute_due_after_payment_change(
            player,
            delta_revert=old_amount if old_affects_due else 0.0,
            delta_apply=new_amount if new_affects_due else 0.0,
        )
        _reset_subscription_after_full_payment(player, payment.payment_date)

        db.session.commit()
        return jsonify(payment.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل تعديل الدفعة: {str(e)}'}), 500
