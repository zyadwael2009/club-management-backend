from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from models import db

def generate_uuid():
    import uuid
    return str(uuid.uuid4())

class User(db.Model):
    """User authentication model - supports superadmin, admin, coach, player roles"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # superadmin, admin, coach, player
    
    # Related entity IDs based on role
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)  # for admin
    player_id = db.Column(db.String(36), db.ForeignKey('players.id'), nullable=True)  # for player
    coach_id = db.Column(db.String(36), db.ForeignKey('coaches.id'), nullable=True)  # for coach
    
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        """Hash and set the password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """Convert user to dictionary (without password hash)"""
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'clubId': self.club_id,
            'playerId': self.player_id,
            'coachId': self.coach_id,
            'isActive': self.is_active,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @staticmethod
    def create_superadmin(username='zyadw', password='ZWL@2009'):
        """Create the superadmin user if it doesn't exist"""
        existing = User.query.filter_by(username=username).first()
        if existing:
            return existing
        
        superadmin = User(
            username=username,
            role='superadmin',
        )
        superadmin.set_password(password)
        db.session.add(superadmin)
        db.session.commit()
        return superadmin


class Coach(db.Model):
    """Coach model for managing coaches"""
    __tablename__ = 'coaches'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    full_name = db.Column(db.String(255), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    monthly_salary = db.Column(db.Float, nullable=True)  # Monthly salary amount
    contact_info = db.Column(db.String(255), nullable=True)  # Phone, email, etc.
    notes = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to user (for authentication)
    user = db.relationship('User', backref='coach_profile', foreign_keys='User.coach_id',
                          lazy='dynamic')
    
    def to_dict(self):
        # Get user info if exists
        user = User.query.filter_by(coach_id=self.id).first()
        
        return {
            'id': self.id,
            'fullName': self.full_name,
            'clubId': self.club_id,
            'monthlySalary': self.monthly_salary,
            'contactInfo': self.contact_info,
            'notes': self.notes,
            'imageUrl': self.image_url,
            'username': user.username if user else None,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class CoachPayment(db.Model):
    """Track monthly salary payments to coaches"""
    __tablename__ = 'coach_payments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    coach_id = db.Column(db.String(36), db.ForeignKey('coaches.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_month = db.Column(db.String(7), nullable=False)  # Format: YYYY-MM (e.g., "2026-04")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'coachId': self.coach_id,
            'amount': self.amount,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'paymentMonth': self.payment_month,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class PlayerPayment(db.Model):
    """Track payments received from players"""
    __tablename__ = 'player_payments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    player_id = db.Column(db.String(36), db.ForeignKey('players.id'), nullable=False)
    amount_paid = db.Column(db.Float, nullable=False)  # Amount received FROM player
    payment_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'playerId': self.player_id,
            'amountPaid': self.amount_paid,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }
