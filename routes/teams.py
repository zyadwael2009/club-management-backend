from flask import Blueprint, request, jsonify
from models import db, Team, Club

teams_bp = Blueprint('teams', __name__)


@teams_bp.route('/', methods=['GET'])
def get_teams():
    """Get all teams, optionally filtered by club_id"""
    club_id = request.args.get('club_id')
    
    query = Team.query
    if club_id:
        query = query.filter_by(club_id=club_id)
    
    teams = query.order_by(Team.min_age).all()
    return jsonify([team.to_dict() for team in teams])


@teams_bp.route('/<team_id>', methods=['GET'])
def get_team(team_id):
    """Get a specific team by ID"""
    team = Team.query.get(team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404
    return jsonify(team.to_dict())


@teams_bp.route('/', methods=['POST'])
def create_team():
    """Create a new team"""
    data = request.get_json()
    
    if not data.get('name'):
        return jsonify({'error': 'Team name is required'}), 400
    
    if not data.get('clubId'):
        return jsonify({'error': 'Club ID is required'}), 400
    
    # Verify club exists
    club = Club.query.get(data['clubId'])
    if not club:
        return jsonify({'error': 'Club not found'}), 404
    
    team = Team(
        name=data['name'],
        club_id=data['clubId'],
        min_age=data.get('minAge', 0),
        max_age=data.get('maxAge', 99),
        description=data.get('description')
    )
    
    db.session.add(team)
    db.session.commit()
    
    return jsonify(team.to_dict()), 201


@teams_bp.route('/<team_id>', methods=['PUT'])
def update_team(team_id):
    """Update a team"""
    team = Team.query.get(team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        team.name = data['name']
    if 'minAge' in data:
        team.min_age = data['minAge']
    if 'maxAge' in data:
        team.max_age = data['maxAge']
    if 'description' in data:
        team.description = data['description']
    
    db.session.commit()
    return jsonify(team.to_dict())


@teams_bp.route('/<team_id>', methods=['DELETE'])
def delete_team(team_id):
    """Delete a team"""
    team = Team.query.get(team_id)
    if not team:
        return jsonify({'error': 'Team not found'}), 404
    
    db.session.delete(team)
    db.session.commit()
    
    return jsonify({'message': 'Team deleted successfully'})


@teams_bp.route('/club/<club_id>', methods=['GET'])
def get_club_teams(club_id):
    """Get all teams for a specific club"""
    club = Club.query.get(club_id)
    if not club:
        return jsonify({'error': 'Club not found'}), 404
    
    teams = Team.query.filter_by(club_id=club_id).order_by(Team.min_age).all()
    return jsonify([team.to_dict() for team in teams])
