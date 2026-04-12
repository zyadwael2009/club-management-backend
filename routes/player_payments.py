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
    if (
        not player.monthly_amount
        or player.monthly_amount <= 0
        or not player.renewal_day
        or not player.next_renewal_date
    ):
        return False

    current_date = today or date.today()
    updated = False
    while player.next_renewal_date <= current_date:
        player.amount_due = (player.amount_due or 0.0) + float(player.monthly_amount)
        player.payment_status = 'unpaid'
        player.next_renewal_date = _add_one_month_keep_day(player.next_renewal_date, player.renewal_day)
        updated = True
    return updated


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

        _apply_player_renewals(player)

        revenue_scope = data.get('revenueScope', 'club')
        if revenue_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع الإيراد يجب أن يكون club أو academy'}), 400

        payment = PlayerPayment(
            player_id=player_id,
            amount_paid=amount_paid,
            revenue_scope=revenue_scope,
            payment_date=datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date(),
            notes=data.get('notes')
        )

        # Keep player due amount in sync with recorded payments.
        _recompute_due_after_payment_change(player, delta_revert=0.0, delta_apply=amount_paid)

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

    # Calculate total paid
    payments = PlayerPayment.query.filter_by(player_id=player_id).all()
    total_paid = sum(payment.amount_paid for payment in payments)
    
    # amount_due is stored as the remaining balance in player profile.
    amount_due = player.amount_due or 0
    outstanding_balance = max(0.0, amount_due)
    
    return jsonify({
        'totalPaid': total_paid,
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

        revenue_scope = data.get('revenueScope', payment.revenue_scope or 'club')
        if revenue_scope not in ['club', 'academy']:
            return jsonify({'error': 'نوع الإيراد يجب أن يكون club أو academy'}), 400

        _apply_player_renewals(player)

        old_amount = float(payment.amount_paid)
        payment.amount_paid = new_amount
        payment.revenue_scope = revenue_scope
        payment.payment_date = datetime.fromisoformat(data['paymentDate'].replace('Z', '+00:00')).date()
        payment.notes = data.get('notes')

        # Undo old payment effect then apply updated one.
        _recompute_due_after_payment_change(player, delta_revert=old_amount, delta_apply=new_amount)

        db.session.commit()
        return jsonify(payment.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'فشل تعديل الدفعة: {str(e)}'}), 500
