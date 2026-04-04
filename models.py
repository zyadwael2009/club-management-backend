from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())


class Club(db.Model):
    __tablename__ = 'clubs'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)
    primary_color = db.Column(db.String(7), default='#2196F3')
    secondary_color = db.Column(db.String(7), default='#FFC107')
    logo_url = db.Column(db.String(500), nullable=True)
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
            'createdAt': self.created_at.isoformat() if self.created_at else None,
            'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
        }


class Subgroup(db.Model):
    """Subgroup (مجموعة فرعية) - categorizes players by type and birth year"""
    __tablename__ = 'subgroups'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    name = db.Column(db.String(255), nullable=False)  # e.g., "أكاديمية 2015"
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=False)
    subgroup_type = db.Column(db.String(20), nullable=False)  # 'academy' (أكاديمية) or 'club' (نادي)
    birth_year = db.Column(db.Integer, nullable=False)  # e.g., 2015, 2014
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
            'subgroupType': self.subgroup_type,
            'birthYear': self.birth_year,
            'description': self.description,
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
    amount_due = db.Column(db.Float, nullable=True)  # Amount left to pay
    notes = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    club_id = db.Column(db.String(36), db.ForeignKey('clubs.id'), nullable=True)
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
        result = {
            'id': self.id,
            'fullName': self.full_name,
            'dateOfBirth': self.date_of_birth.isoformat() if self.date_of_birth else None,
            'paymentStatus': self.payment_status,
            'amountDue': self.amount_due,
            'notes': self.notes,
            'imageUrl': self.image_url,
            'clubId': self.club_id,
            'subgroupId': self.subgroup_id,
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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    # Snapshot of player data at check-in time
    player_name = db.Column(db.String(255))
    player_payment_status = db.Column(db.String(20))
    
    def to_dict(self):
        return {
            'id': self.id,
            'playerId': self.player_id,
            'clubId': self.club_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'playerSnapshot': {
                'fullName': self.player_name,
                'paymentStatus': self.player_payment_status,
            }
        }
