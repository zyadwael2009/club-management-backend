from flask import Blueprint, request, jsonify, session
from models import db, Player, PlayerPayment, User
from routes.auth import login_required, admin_or_superadmin_required
from datetime import datetime

player_payments = Blueprint('player_payments', __name__)


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
        current_due = player.amount_due or 0.0
        player.amount_due = max(0.0, current_due - amount_paid)
        player.payment_status = 'paid' if player.amount_due <= 0 else 'unpaid'

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
        if player.amount_due is None:
            player.amount_due = 0.0

        # Revert due amount when deleting a payment to preserve consistency.
        player.amount_due = player.amount_due + payment.amount_paid
        player.payment_status = 'paid' if player.amount_due <= 0 else 'unpaid'

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
