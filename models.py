from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())


class Season(db.Model):
    __tablename__ = 'seasons'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    is_current = db.Column(db.Boolean, default=False, nullable=False)
    created_by_user_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'isCurrent': bool(self.is_current),
            'createdByUserId': self.created_by_user_id,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class Club(db.Model):
    __tablename__ = 'clubs'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    primary_color = db.Column(db.String(7), default='#2196F3')
    secondary_color = db.Column(db.String(7), default='#FFC107')
    logo_url = db.Column(db.String(500), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    monthly_amount = db.Column(db.Float, nullable=True)
    max_branches = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    deactivated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    subgroups = db.relationship('Subgroup', backref='club', lazy='dynamic', cascade='all, delete-orphan')
    players = db.relationship('Player', backref='club', lazy='dynamic', cascade='all, delete-orphan')
    checkins = db.relationship('CheckIn', backref='club', lazy='dynamic', cascade='all, delete-orphan')
    matches = db.relationship('Match', backref='club', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'primaryColor': self.primary_color,
            'secondaryColor': self.secondary_color,
            'logoUrl': self.logo_url,
            'dueDate': self.due_date.isoformat() if self.due_date else None,
            'monthlyAmount': self.monthly_amount,
            'maxBranches': self.max_branches,
            'isActive': self.is_active,
            'deactivatedAt': self.deactivated_at.isoformat() if self.deactivated_at else None,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class Branch(db.Model):
    __tablename__ = 'branches'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    manager_user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'clubId': self.club_id,
            'managerUserId': self.manager_user_id,
            'isActive': bool(self.is_active),
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class Subgroup(db.Model):
    """Subgroup (مجموعة فرعية) - categorizes players by type and birth year"""
    __tablename__ = 'subgroups'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)  # e.g., "أكاديمية 2015"
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    subgroup_type = db.Column(db.String(20), nullable=False)  # 'academy' (أكاديمية) or 'club' (نادي)
    birth_year = db.Column(db.Integer, nullable=False)  # e.g., 2015, 2014
    monthly_amount = db.Column(db.Float, nullable=True)  # Academy monthly amount for subgroup
    league_amount = db.Column(db.Float, nullable=True)  # Default league due for players in subgroup
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', backref='subgroup', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'subgroupType': self.subgroup_type,
            'birthYear': self.birth_year,
            'monthlyAmount': self.monthly_amount,
            'leagueAmount': self.league_amount,
            'description': self.description,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class Training(db.Model):
    """Training session that can target one or more subgroups"""
    __tablename__ = 'trainings'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    subgroup_id = db.Column(db.String(36), db.ForeignKey('subgroups.id'), nullable=False)
    season_id = db.Column(db.String(36), nullable=True)
    training_scope = db.Column(db.String(20), nullable=False, default='club')  # club | academy | first_team
    training_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.String(5), nullable=True)  # HH:MM (optional)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def assigned_subgroup_ids(self):
        links = TrainingSubgroup.query.filter_by(training_id=self.id).all()
        subgroup_ids = [link.subgroup_id for link in links if link.subgroup_id]
        if self.subgroup_id and self.subgroup_id not in subgroup_ids:
            subgroup_ids.insert(0, self.subgroup_id)

        ordered = []
        seen = set()
        for subgroup_id in subgroup_ids:
            if subgroup_id not in seen:
                seen.add(subgroup_id)
                ordered.append(subgroup_id)
        return ordered

    def assigned_subgroup_names(self):
        subgroup_ids = self.assigned_subgroup_ids()
        if not subgroup_ids:
            return []

        subgroups = Subgroup.query.filter(Subgroup.id.in_(subgroup_ids)).all()
        subgroup_name_map = {subgroup.id: subgroup.name for subgroup in subgroups}
        return [subgroup_name_map[subgroup_id] for subgroup_id in subgroup_ids if subgroup_id in subgroup_name_map]

    def to_dict(self):
        subgroup_ids = self.assigned_subgroup_ids()
        return {
            'id': self.id,
            'name': self.name,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'subgroupId': self.subgroup_id,
            'seasonId': self.season_id,
            'subgroupIds': subgroup_ids,
            'subgroupNames': self.assigned_subgroup_names(),
            'trainingScope': self.training_scope or 'club',
            'trainingDate': self.training_date.isoformat() if self.training_date else None,
            'startTime': self.start_time,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


# Association table for Match-Player many-to-many relationship
match_players = db.Table('match_players',
    db.Column('match_id', db.String(36), db.ForeignKey('matches.id'), primary_key=True),
    db.Column('player_id', db.String(36), db.ForeignKey('players.id'), primary_key=True)
)


class Match(db.Model):
    """Match (مباراة) - tracks games played"""
    __tablename__ = 'matches'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    match_type = db.Column(db.String(20), nullable=False)  # 'friendly' (ودي) or 'official' (رسمي)
    opponent_name = db.Column(db.String(255), nullable=False)  # اسم الفريق المنافس
    match_date = db.Column(db.Date, nullable=False)
    our_score = db.Column(db.Integer, nullable=True)
    opponent_score = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    subgroup_id = db.Column(db.String(36), db.ForeignKey('subgroups.id'), nullable=True)  # Optional: link to subgroup
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    players = db.relationship('Player', secondary=match_players, lazy='dynamic',
                             backref=db.backref('matches', lazy='dynamic'))
    
    def to_dict(self, include_players=False):
        result = {
            'id': self.id,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'matchType': self.match_type,
            'opponentName': self.opponent_name,
            'matchDate': self.match_date.isoformat() if self.match_date else None,
            'ourScore': self.our_score,
            'opponentScore': self.opponent_score,
            'notes': self.notes,
            'subgroupId': self.subgroup_id,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_players:
            result['playerIds'] = [p.id for p in self.players]
        return result


class Player(db.Model):
    __tablename__ = 'players'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    full_name = db.Column(db.String(255), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    payment_status = db.Column(db.String(20), default='unpaid')  # 'paid' or 'unpaid'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    paused_at = db.Column(db.DateTime, nullable=True)
    paused_amount_due = db.Column(db.Float, nullable=True)
    paused_league_due = db.Column(db.Float, nullable=True)
    amount_due = db.Column(db.Float, nullable=True)  # Amount left to pay
    monthly_amount = db.Column(db.Float, nullable=True)  # Monthly academy fee
    league_due = db.Column(db.Float, nullable=True)  # Remaining league subscription due
    renewal_day = db.Column(db.Integer, nullable=True)  # Day of month for auto renewal
    next_renewal_date = db.Column(db.Date, nullable=True)  # Next scheduled renewal date
    subscription_start_date = db.Column(db.Date, nullable=True)
    subscription_end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    phone_number = db.Column(db.String(30), nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    subgroup_id = db.Column(db.String(36), db.ForeignKey('subgroups.id'), nullable=True)
    pin = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    checkins = db.relationship('CheckIn', backref='player', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def qr_code(self):
        return f'CLUB_PLAYER_{self.id}'
    
    def get_match_stats(self):
        """Get player's match statistics"""
        all_matches = self.matches.all()
        friendly_count = sum(1 for m in all_matches if m.match_type == 'friendly')
        official_count = sum(1 for m in all_matches if m.match_type == 'official')
        return {
            'totalMatches': len(all_matches),
            'friendlyMatches': friendly_count,
            'officialMatches': official_count,
        }
    
    def to_dict(self, include_match_stats=False):
        user = User.query.filter_by(player_id=self.id).first()
        result = {
            'id': self.id,
            'fullName': self.full_name,
            'dateOfBirth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'paymentStatus': self.payment_status,
            'isActive': bool(self.is_active),
            'pausedAt': self.paused_at.isoformat() if self.paused_at else None,
            'amountDue': self.amount_due,
            'pausedAmountDue': self.paused_amount_due,
            'monthlyAmount': self.monthly_amount,
            'leagueDue': self.league_due,
            'pausedLeagueDue': self.paused_league_due,
            'renewalDay': self.renewal_day,
            'nextRenewalDate': self.next_renewal_date.isoformat() if self.next_renewal_date else None,
            'subscriptionStartDate': self.subscription_start_date.isoformat() if self.subscription_start_date else None,
            'subscriptionEndDate': self.subscription_end_date.isoformat() if self.subscription_end_date else None,
            'notes': self.notes,
            'phoneNumber': self.phone_number,
            'imageUrl': self.image_url,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'subgroupId': self.subgroup_id,
            'subgroupName': self.subgroup.name if self.subgroup else None,
            'subgroupType': self.subgroup.subgroup_type if self.subgroup else None,
            'username': user.username if user else None,
            'pin': self.pin,
            'qrCode': self.qr_code,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_match_stats:
            result['matchStats'] = self.get_match_stats()
        return result


class CheckIn(db.Model):
    __tablename__ = 'checkins'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    player_id = db.Column(db.String(36), db.ForeignKey('players.id'), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # Snapshot of player data at check-in time
    player_name = db.Column(db.String(255))
    player_payment_status = db.Column(db.String(20))
    
    def to_dict(self):
        return {
            'id': self.id,
            'playerId': self.player_id,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'playerSnapshot': {
                'fullName': self.player_name,
                'paymentStatus': self.player_payment_status,
            }
        }


class CheckInTraining(db.Model):
    """Links each check-in to the selected training session"""
    __tablename__ = 'checkin_trainings'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    checkin_id = db.Column(db.String(36), db.ForeignKey('checkins.id'), nullable=False, unique=True)
    training_id = db.Column(db.String(36), db.ForeignKey('trainings.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrainingSubgroup(db.Model):
    """Links training sessions to one or more assigned subgroups"""
    __tablename__ = 'training_subgroups'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    training_id = db.Column(db.String(36), db.ForeignKey('trainings.id'), nullable=False)
    subgroup_id = db.Column(db.String(36), db.ForeignKey('subgroups.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('training_id', 'subgroup_id', name='uq_training_subgroup_link'),
    )


# ==================== AUTHENTICATION & AUTHORIZATION ====================

class User(db.Model):
    """User authentication model - supports superadmin, admin, coach, player roles"""
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # superadmin, admin, coach, player
    
    # Related entity IDs based on role
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)  # for admin
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)  # for branch manager / scoped users
    player_id = db.Column(db.String(36), db.ForeignKey('players.id'), nullable=True)  # for player
    coach_id = db.Column(db.String(36), nullable=True)  # for coach (FK will be added after Coach model)
    employee_id = db.Column(db.String(36), db.ForeignKey('employees.id'), nullable=True)  # for employee
    
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
            'branchId': self.branch_id,
            'playerId': self.player_id,
            'coachId': self.coach_id,
            'employeeId': self.employee_id,
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
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deactivated_at = db.Column(db.DateTime, nullable=True)
    monthly_salary = db.Column(db.Float, nullable=True)  # Monthly salary amount
    contact_info = db.Column(db.String(255), nullable=True)  # Phone, email, etc.
    notes = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def qr_code(self):
        return f'CLUB_COACH_{self.id}'
    
    def to_dict(self):
        # Get user info if exists
        user = User.query.filter_by(coach_id=self.id).first()
        
        return {
            'id': self.id,
            'fullName': self.full_name,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'isActive': bool(self.is_active),
            'deactivatedAt': self.deactivated_at.isoformat() if self.deactivated_at else None,
            'monthlySalary': self.monthly_salary,
            'contactInfo': self.contact_info,
            'notes': self.notes,
            'imageUrl': self.image_url,
            'qrCode': self.qr_code,
            'username': user.username if user else None,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class CoachCheckIn(db.Model):
    """Coach attendance records"""
    __tablename__ = 'coach_checkins'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    coach_id = db.Column(db.String(36), db.ForeignKey('coaches.id'), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    coach_name = db.Column(db.String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'coachId': self.coach_id,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'coachSnapshot': {
                'fullName': self.coach_name,
            },
        }


class CoachPayment(db.Model):
    """Track monthly salary payments to coaches"""
    __tablename__ = 'coach_payments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    coach_id = db.Column(db.String(36), db.ForeignKey('coaches.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_month = db.Column(db.String(7), nullable=False)  # Format: YYYY-MM (e.g., "2026-04")
    expense_scope = db.Column(db.String(20), nullable=False, default='club')  # club | academy
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'coachId': self.coach_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'amount': self.amount,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'paymentMonth': self.payment_month,
            'expenseScope': self.expense_scope,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class PlayerPayment(db.Model):
    """Track payments received from players"""
    __tablename__ = 'player_payments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    player_id = db.Column(db.String(36), db.ForeignKey('players.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    amount_paid = db.Column(db.Float, nullable=False)  # Amount received FROM player
    revenue_scope = db.Column(db.String(20), nullable=False, default='club')  # club | academy
    payment_type = db.Column(db.String(30), nullable=True)  # league_subscription | monthly_subscription | clothing_bag
    payment_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'playerId': self.player_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'amountPaid': self.amount_paid,
            'revenueScope': self.revenue_scope,
            'paymentType': self.payment_type,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


class MatchExpense(db.Model):
    """Track expenses paid for matches (transport, ambulance, field rent, etc.)"""
    __tablename__ = 'match_expenses'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    match_id = db.Column(db.String(36), db.ForeignKey('matches.id'), nullable=False)
    season_id = db.Column(db.String(36), nullable=True)
    expense_type = db.Column(db.String(30), nullable=False)  # transportation | ambulance | field_rent
    expense_scope = db.Column(db.String(20), nullable=False, default='club')  # club | academy
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        match = Match.query.get(self.match_id)
        return {
            'id': self.id,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'matchId': self.match_id,
            'seasonId': self.season_id,
            'expenseType': self.expense_type,
            'expenseScope': self.expense_scope,
            'amount': self.amount,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'matchSnapshot': {
                'opponentName': match.opponent_name if match else None,
                'matchDate': match.match_date.isoformat() if match and match.match_date else None,
                'matchType': match.match_type if match else None,
            },
        }


class GeneralExpense(db.Model):
    """Track non-match operational expenses (training field rent, clothing)."""
    __tablename__ = 'general_expenses'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    expense_type = db.Column(db.String(40), nullable=False)  # training_field_rent | clothing
    expense_scope = db.Column(db.String(20), nullable=False, default='club')  # club | academy
    amount = db.Column(db.Float, nullable=False)
    budget_amount = db.Column(db.Float, nullable=True)  # primarily for clothing expense
    payment_date = db.Column(db.Date, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'expenseType': self.expense_type,
            'expenseScope': self.expense_scope,
            'amount': self.amount,
            'budgetAmount': self.budget_amount,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }

class Employee(db.Model):
    """Employee model for managing staff"""
    __tablename__ = 'employees'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    full_name = db.Column(db.String(255), nullable=False)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    role = db.Column(db.String(100), nullable=False)  # Manually entered role
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deactivated_at = db.Column(db.DateTime, nullable=True)
    monthly_salary = db.Column(db.Float, nullable=True)
    contact_info = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        user = User.query.filter_by(employee_id=self.id).first()
        return {
            'id': self.id,
            'fullName': self.full_name,
            'clubId': self.club_id,
            'branchId': self.branch_id,
            'role': self.role,
            'isActive': bool(self.is_active),
            'deactivatedAt': self.deactivated_at.isoformat() if self.deactivated_at else None,
            'monthlySalary': self.monthly_salary,
            'contactInfo': self.contact_info,
            'notes': self.notes,
            'imageUrl': self.image_url,
            'username': user.username if user else None,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }

class EmployeePayment(db.Model):
    """Track monthly salary payments to employees"""
    __tablename__ = 'employee_payments'

    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    employee_id = db.Column(db.String(36), db.ForeignKey('employees.id'), nullable=False)
    branch_id = db.Column(db.String(36), db.ForeignKey('branches.id'), nullable=True)
    season_id = db.Column(db.String(36), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_month = db.Column(db.String(7), nullable=False)  # YYYY-MM
    expense_scope = db.Column(db.String(20), nullable=False, default='club')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'employeeId': self.employee_id,
            'branchId': self.branch_id,
            'seasonId': self.season_id,
            'amount': self.amount,
            'paymentDate': self.payment_date.isoformat() if self.payment_date else None,
            'paymentMonth': self.payment_month,
            'expenseScope': self.expense_scope,
            'notes': self.notes,
            'createdAt': self.created_at.isoformat() if self.created_at else None,
        }


