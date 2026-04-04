from flask import Blueprint, request, jsonify
from models import db, Club
from datetime import datetime

clubs_bp = Blueprint('clubs', __name__)


@clubs_bp.route('', methods=['GET'])
def get_clubs():
    """Get all clubs, ordered by creation date (newest first)"""
    clubs = Club.query.order_by(Club.created_at.desc()).all()
    return jsonify([club.to_dict() for club in clubs])


@clubs_bp.route('/<club_id>', methods=['GET'])
def get_club(club_id):
    """Get a single club by ID"""
    club = Club.query.get_or_404(club_id)
    return jsonify(club.to_dict())


@clubs_bp.route('', methods=['POST'])
def create_club():
    """Create a new club"""
    data = request.get_json()
    
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    
    club = Club(
        name=data['name'],
        primary_color=data.get('primaryColor', '#2196F3'),
        secondary_color=data.get('secondaryColor', '#FFC107'),
        logo_url=data.get('logoUrl'),
    )
    
    db.session.add(club)
    db.session.commit()
    
    return jsonify(club.to_dict()), 201


@clubs_bp.route('/<club_id>', methods=['PUT'])
def update_club(club_id):
    """Update an existing club"""
    club = Club.query.get_or_404(club_id)
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    if 'name' in data:
        club.name = data['name']
    if 'primaryColor' in data:
        club.primary_color = data['primaryColor']
    if 'secondaryColor' in data:
        club.secondary_color = data['secondaryColor']
    if 'logoUrl' in data:
        club.logo_url = data['logoUrl']
    
    club.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify(club.to_dict())


@clubs_bp.route('/<club_id>', methods=['DELETE'])
def delete_club(club_id):
    """Delete a club and all associated data"""
    club = Club.query.get_or_404(club_id)
    
    db.session.delete(club)
    db.session.commit()
    
    return jsonify({'message': 'Club deleted successfully'})
