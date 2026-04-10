import os
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from config import Config
from models import db, User
from sqlalchemy import inspect, text


def _ensure_schema_updates():
    inspector = inspect(db.engine)
    columns = {col['name'] for col in inspector.get_columns('clubs')}
    player_payment_columns = {col['name'] for col in inspector.get_columns('player_payments')}
    coach_payment_columns = {col['name'] for col in inspector.get_columns('coach_payments')}
    match_expense_columns = set()
    training_columns = set()
    if 'match_expenses' in inspector.get_table_names():
        match_expense_columns = {col['name'] for col in inspector.get_columns('match_expenses')}
    if 'trainings' in inspector.get_table_names():
        training_columns = {col['name'] for col in inspector.get_columns('trainings')}

    statements = []
    if 'due_date' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN due_date DATE")
    if 'is_active' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'deactivated_at' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN deactivated_at DATETIME")
    if 'revenue_scope' not in player_payment_columns:
        statements.append("ALTER TABLE player_payments ADD COLUMN revenue_scope VARCHAR(20) DEFAULT 'club'")
    if 'expense_scope' not in coach_payment_columns:
        statements.append("ALTER TABLE coach_payments ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'club'")
    if 'expense_scope' not in match_expense_columns and 'match_expenses' in inspector.get_table_names():
        statements.append("ALTER TABLE match_expenses ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'club'")
    if 'training_scope' not in training_columns and 'trainings' in inspector.get_table_names():
        statements.append("ALTER TABLE trainings ADD COLUMN training_scope VARCHAR(20) DEFAULT 'club'")

    for stmt in statements:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from routes import clubs_bp, players_bp, checkins_bp, uploads_bp, subgroups_bp, matches_bp
    from routes.auth import auth
    from routes.coaches import coaches
    from routes.player_payments import player_payments
    from routes.trainings import trainings_bp
    
    app.register_blueprint(auth, url_prefix='/api/auth')
    app.register_blueprint(clubs_bp, url_prefix='/api/clubs')
    app.register_blueprint(players_bp, url_prefix='/api/players')
    app.register_blueprint(checkins_bp, url_prefix='/api/checkins')
    app.register_blueprint(uploads_bp, url_prefix='/api/images')
    app.register_blueprint(subgroups_bp, url_prefix='/api/subgroups')
    app.register_blueprint(matches_bp, url_prefix='/api/matches')
    app.register_blueprint(coaches, url_prefix='/api/coaches')
    app.register_blueprint(player_payments, url_prefix='/api/players')  # Nested under /api/players
    app.register_blueprint(trainings_bp, url_prefix='/api/trainings')

    @app.route('/')
    def root():
        return jsonify({
            'message': 'Club Management API is running',
            'health': '/api/health',
            'base': '/api',
            'privacy_policy': '/privacy-policy',
            'delete_account': '/delete-account',
        })

    @app.route('/api')
    def api_root():
        return jsonify({
            'message': 'Club Management API base endpoint',
            'health': '/api/health',
            'privacy_policy': '/privacy-policy',
            'delete_account': '/delete-account',
        })

    @app.route('/privacy-policy')
    @app.route('/privacy-policy.html')
    def privacy_policy_page():
        return render_template('privacy_policy.html')

    @app.route('/delete-account')
    @app.route('/delete-account.html')
    def delete_account_page():
        return render_template('delete_account.html')
    
    # Health check endpoint
    @app.route('/api/health')
    def health_check():
        return jsonify({'status': 'healthy', 'message': 'Club Management API is running'})
    
    # Create database tables and superadmin
    with app.app_context():
        db.create_all()
        _ensure_schema_updates()
        # Create superadmin if not exists
        User.create_superadmin(username='zyadw', password='ZWL@2009')
        print("Database initialized and superadmin created (zyadw/ZWL@2009)")
    
    return app


# Create app instance for running directly
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

