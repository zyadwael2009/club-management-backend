import os
from flask import Flask, jsonify
from flask_cors import CORS
from config import Config
from models import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    CORS(app, origins=app.config['CORS_ORIGINS'])
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from routes import clubs_bp, players_bp, checkins_bp, uploads_bp, subgroups_bp, matches_bp
    
    app.register_blueprint(clubs_bp, url_prefix='/api/clubs')
    app.register_blueprint(players_bp, url_prefix='/api/players')
    app.register_blueprint(checkins_bp, url_prefix='/api/checkins')
    app.register_blueprint(uploads_bp, url_prefix='/api/images')
    app.register_blueprint(subgroups_bp, url_prefix='/api/subgroups')
    app.register_blueprint(matches_bp, url_prefix='/api/matches')
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        return jsonify({'status': 'healthy', 'message': 'Club Management API is running'})
    
    # Create database tables
    with app.app_context():
        db.create_all()
    
    return app


# Create app instance for running directly
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
