import os
from flask import Flask, jsonify, render_template, request, session, send_from_directory
from flask_cors import CORS
from config import Config
from models import db, User, Season
from sqlalchemy import inspect, text
from datetime import datetime


def _ensure_schema_updates():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    columns = {col['name'] for col in inspector.get_columns('clubs')}
    player_columns = {col['name'] for col in inspector.get_columns('players')}
    coach_columns = {col['name'] for col in inspector.get_columns('coaches')} if 'coaches' in table_names else set()
    subgroup_columns = {col['name'] for col in inspector.get_columns('subgroups')}
    employee_columns = {col['name'] for col in inspector.get_columns('employees')} if 'employees' in table_names else set()
    user_columns = {col['name'] for col in inspector.get_columns('users')} if 'users' in table_names else set()
    player_payment_columns = {col['name'] for col in inspector.get_columns('player_payments')}
    coach_payment_columns = {col['name'] for col in inspector.get_columns('coach_payments')}
    employee_payment_columns = {col['name'] for col in inspector.get_columns('employee_payments')} if 'employee_payments' in table_names else set()
    match_expense_columns = set()
    general_expense_columns = set()
    checkin_columns = set()
    match_columns = set()
    coach_checkin_columns = set()
    employee_checkin_columns = set()
    training_columns = set()
    branch_columns = {col['name'] for col in inspector.get_columns('branches')} if 'branches' in table_names else set()
    if 'match_expenses' in table_names:
        match_expense_columns = {col['name'] for col in inspector.get_columns('match_expenses')}
    if 'general_expenses' in table_names:
        general_expense_columns = {col['name'] for col in inspector.get_columns('general_expenses')}
    if 'checkins' in table_names:
        checkin_columns = {col['name'] for col in inspector.get_columns('checkins')}
    if 'matches' in table_names:
        match_columns = {col['name'] for col in inspector.get_columns('matches')}
    if 'coach_checkins' in table_names:
        coach_checkin_columns = {col['name'] for col in inspector.get_columns('coach_checkins')}
    if 'employee_checkins' in table_names:
        employee_checkin_columns = {col['name'] for col in inspector.get_columns('employee_checkins')}
    if 'trainings' in table_names:
        training_columns = {col['name'] for col in inspector.get_columns('trainings')}

    statements = []
    if 'due_date' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN due_date DATE")
    if 'is_active' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'deactivated_at' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN deactivated_at DATETIME")
    if 'monthly_amount' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN monthly_amount FLOAT")
    if 'max_branches' not in columns:
        statements.append("ALTER TABLE clubs ADD COLUMN max_branches INTEGER")
    if 'revenue_scope' not in player_payment_columns:
        statements.append("ALTER TABLE player_payments ADD COLUMN revenue_scope VARCHAR(20) DEFAULT 'club'")
    if 'payment_type' not in player_payment_columns:
        statements.append("ALTER TABLE player_payments ADD COLUMN payment_type VARCHAR(30)")
    if 'phone_number' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN phone_number VARCHAR(30)")
    if 'is_active' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'paused_at' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN paused_at DATETIME")
    if 'paused_amount_due' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN paused_amount_due FLOAT")
    if 'paused_league_due' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN paused_league_due FLOAT")
    if 'monthly_amount' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN monthly_amount FLOAT")
    if 'renewal_day' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN renewal_day INTEGER")
    if 'next_renewal_date' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN next_renewal_date DATE")
    if 'subscription_start_date' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN subscription_start_date DATE")
    if 'subscription_end_date' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN subscription_end_date DATE")
    if 'custom_code' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN custom_code VARCHAR(120)")
    if 'monthly_amount' not in subgroup_columns:
        statements.append("ALTER TABLE subgroups ADD COLUMN monthly_amount FLOAT")
    if 'is_active' not in coach_columns and 'coaches' in table_names:
        statements.append("ALTER TABLE coaches ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'deactivated_at' not in coach_columns and 'coaches' in table_names:
        statements.append("ALTER TABLE coaches ADD COLUMN deactivated_at DATETIME")
    if 'custom_code' not in coach_columns and 'coaches' in table_names:
        statements.append("ALTER TABLE coaches ADD COLUMN custom_code VARCHAR(120)")
    if 'permissions_json' not in coach_columns and 'coaches' in table_names:
        statements.append("ALTER TABLE coaches ADD COLUMN permissions_json TEXT")
    if 'league_amount' not in subgroup_columns:
        statements.append("ALTER TABLE subgroups ADD COLUMN league_amount FLOAT")
    if 'league_due' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN league_due FLOAT")
    if 'branch_id' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN branch_id VARCHAR(36)")
    if 'is_active' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'deactivated_at' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN deactivated_at DATETIME")
    if 'monthly_salary' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN monthly_salary FLOAT")
    if 'contact_info' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN contact_info VARCHAR(255)")
    if 'notes' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN notes TEXT")
    if 'image_url' not in employee_columns and 'employees' in table_names:
        statements.append("ALTER TABLE employees ADD COLUMN image_url VARCHAR(500)")
    if 'expense_scope' not in coach_payment_columns:
        statements.append("ALTER TABLE coach_payments ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'club'")
    if 'expense_scope' not in match_expense_columns and 'match_expenses' in table_names:
        statements.append("ALTER TABLE match_expenses ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'club'")
    if 'training_scope' not in training_columns and 'trainings' in table_names:
        statements.append("ALTER TABLE trainings ADD COLUMN training_scope VARCHAR(20) DEFAULT 'club'")
    if 'start_time' not in training_columns and 'trainings' in table_names:
        statements.append("ALTER TABLE trainings ADD COLUMN start_time VARCHAR(5)")
    if 'season_id' not in training_columns and 'trainings' in table_names:
        statements.append("ALTER TABLE trainings ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in checkin_columns and 'checkins' in table_names:
        statements.append("ALTER TABLE checkins ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in match_columns and 'matches' in table_names:
        statements.append("ALTER TABLE matches ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in player_payment_columns:
        statements.append("ALTER TABLE player_payments ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in coach_payment_columns:
        statements.append("ALTER TABLE coach_payments ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in coach_checkin_columns and 'coach_checkins' in table_names:
        statements.append("ALTER TABLE coach_checkins ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in employee_checkin_columns and 'employee_checkins' in table_names:
        statements.append("ALTER TABLE employee_checkins ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in match_expense_columns and 'match_expenses' in table_names:
        statements.append("ALTER TABLE match_expenses ADD COLUMN season_id VARCHAR(36)")
    if 'season_id' not in general_expense_columns and 'general_expenses' in table_names:
        statements.append("ALTER TABLE general_expenses ADD COLUMN season_id VARCHAR(36)")
    if 'training_subgroups' not in table_names:
        statements.append(
            "CREATE TABLE training_subgroups ("
            "id VARCHAR(36) PRIMARY KEY, "
            "training_id VARCHAR(36) NOT NULL, "
            "subgroup_id VARCHAR(36) NOT NULL, "
            "created_at DATETIME, "
            "UNIQUE(training_id, subgroup_id), "
            "FOREIGN KEY(training_id) REFERENCES trainings(id), "
            "FOREIGN KEY(subgroup_id) REFERENCES subgroups(id)"
            ")"
        )
    if 'seasons' not in table_names:
        statements.append(
            "CREATE TABLE seasons ("
            "id VARCHAR(36) PRIMARY KEY, "
            "name VARCHAR(255) NOT NULL, "
            "is_current BOOLEAN DEFAULT 0, "
            "created_by_user_id VARCHAR(36), "
            "created_at DATETIME, "
            "updated_at DATETIME"
            ")"
        )
    if 'branches' not in table_names:
        statements.append(
            "CREATE TABLE branches ("
            "id VARCHAR(36) PRIMARY KEY, "
            "name VARCHAR(255) NOT NULL, "
            "club_id VARCHAR(36) NOT NULL, "
            "manager_user_id VARCHAR(36), "
            "is_active BOOLEAN DEFAULT 1, "
            "created_at DATETIME, "
            "updated_at DATETIME"
            ")"
        )
    if 'employees' not in table_names:
        statements.append(
            "CREATE TABLE employees ("
            "id VARCHAR(36) PRIMARY KEY, "
            "full_name VARCHAR(255) NOT NULL, "
            "club_id VARCHAR(36) NOT NULL, "
            "branch_id VARCHAR(36), "
            "role VARCHAR(100) NOT NULL, "
            "is_active BOOLEAN DEFAULT 1, "
            "deactivated_at DATETIME, "
            "monthly_salary FLOAT, "
            "contact_info VARCHAR(255), "
            "notes TEXT, "
            "image_url VARCHAR(500), "
            "created_at DATETIME, "
            "updated_at DATETIME"
            ")"
        )
    if 'employee_payments' not in table_names:
        statements.append(
            "CREATE TABLE employee_payments ("
            "id VARCHAR(36) PRIMARY KEY, "
            "employee_id VARCHAR(36) NOT NULL, "
            "branch_id VARCHAR(36), "
            "season_id VARCHAR(36), "
            "amount FLOAT NOT NULL, "
            "payment_date DATE NOT NULL, "
            "payment_month VARCHAR(7) NOT NULL, "
            "expense_scope VARCHAR(20) DEFAULT 'club', "
            "notes TEXT, "
            "created_at DATETIME, "
            "FOREIGN KEY(employee_id) REFERENCES employees(id)"
            ")"
        )
    if 'employee_checkins' not in table_names:
        statements.append(
            "CREATE TABLE employee_checkins ("
            "id VARCHAR(36) PRIMARY KEY, "
            "employee_id VARCHAR(36) NOT NULL, "
            "club_id VARCHAR(36), "
            "branch_id VARCHAR(36), "
            "season_id VARCHAR(36), "
            "timestamp DATETIME, "
            "employee_name VARCHAR(255), "
            "FOREIGN KEY(employee_id) REFERENCES employees(id)"
            ")"
        )
    if 'branch_id' not in user_columns and 'users' in table_names:
        statements.append("ALTER TABLE users ADD COLUMN branch_id VARCHAR(36)")
    if 'employee_id' not in user_columns and 'users' in table_names:
        statements.append("ALTER TABLE users ADD COLUMN employee_id VARCHAR(36)")
    if 'session_token' not in user_columns and 'users' in table_names:
        statements.append("ALTER TABLE users ADD COLUMN session_token VARCHAR(120)")
    if 'branch_id' not in player_columns:
        statements.append("ALTER TABLE players ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in subgroup_columns:
        statements.append("ALTER TABLE subgroups ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in coach_columns and 'coaches' in table_names:
        statements.append("ALTER TABLE coaches ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in training_columns and 'trainings' in table_names:
        statements.append("ALTER TABLE trainings ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in match_columns and 'matches' in table_names:
        statements.append("ALTER TABLE matches ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in checkin_columns and 'checkins' in table_names:
        statements.append("ALTER TABLE checkins ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in coach_checkin_columns and 'coach_checkins' in table_names:
        statements.append("ALTER TABLE coach_checkins ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in employee_checkin_columns and 'employee_checkins' in table_names:
        statements.append("ALTER TABLE employee_checkins ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in player_payment_columns:
        statements.append("ALTER TABLE player_payments ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in coach_payment_columns:
        statements.append("ALTER TABLE coach_payments ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in employee_payment_columns and 'employee_payments' in table_names:
        statements.append("ALTER TABLE employee_payments ADD COLUMN branch_id VARCHAR(36)")
    if 'season_id' not in employee_payment_columns and 'employee_payments' in table_names:
        statements.append("ALTER TABLE employee_payments ADD COLUMN season_id VARCHAR(36)")
    if 'expense_scope' not in employee_payment_columns and 'employee_payments' in table_names:
        statements.append("ALTER TABLE employee_payments ADD COLUMN expense_scope VARCHAR(20) DEFAULT 'club'")
    if 'branch_id' not in match_expense_columns and 'match_expenses' in table_names:
        statements.append("ALTER TABLE match_expenses ADD COLUMN branch_id VARCHAR(36)")
    if 'branch_id' not in general_expense_columns and 'general_expenses' in table_names:
        statements.append("ALTER TABLE general_expenses ADD COLUMN branch_id VARCHAR(36)")

    for stmt in statements:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()


def _ensure_default_season():
    current = Season.query.filter_by(is_current=True).order_by(Season.updated_at.desc()).first()
    if current:
        return current

    existing = Season.query.order_by(Season.created_at.asc()).first()
    if existing:
        existing.is_current = True
        db.session.commit()
        return existing

    default_name = f"Season {datetime.utcnow().year}"
    season = Season(name=default_name, is_current=True)
    db.session.add(season)
    db.session.commit()
    return season


def _backfill_legacy_season_ids(current_season_id):
    if not current_season_id:
        return

    statements = [
        f"UPDATE trainings SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE checkins SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE matches SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE player_payments SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE coach_payments SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE coach_checkins SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE employee_checkins SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE match_expenses SET season_id = '{current_season_id}' WHERE season_id IS NULL",
        f"UPDATE general_expenses SET season_id = '{current_season_id}' WHERE season_id IS NULL",
    ]

    for stmt in statements:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    web_build_dir = os.environ.get('WEB_BUILD_DIR') or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'web',
    )
    app.config['WEB_BUILD_DIR'] = web_build_dir

    def _web_ready():
        return os.path.isfile(os.path.join(web_build_dir, 'index.html'))
    
    # Initialize extensions
    db.init_app(app)
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)

    @app.before_request
    def _load_session_from_web_token():
        if 'user_id' in session:
            return

        token = request.headers.get('X-Session-Token')
        serializer = app.session_interface.get_signing_serializer(app)
        if token and serializer:
            try:
                data = serializer.loads(token)
                session.clear()
                session.update(data)
                if 'user_id' in session:
                    return
            except Exception:
                session.clear()

        # Last-resort fallback for web clients if signed token is unavailable.
        user_id = request.headers.get('X-Session-UserId')
        if user_id:
            session['user_id'] = user_id
    
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from routes import clubs_bp, players_bp, checkins_bp, uploads_bp, subgroups_bp, matches_bp, branches_bp, employees_bp
    from routes.auth import auth
    from routes.coaches import coaches
    from routes.player_payments import player_payments
    from routes.trainings import trainings_bp
    from routes.seasons import seasons_bp

    app.register_blueprint(auth, url_prefix='/api/auth')
    app.register_blueprint(clubs_bp, url_prefix='/api/clubs')
    app.register_blueprint(players_bp, url_prefix='/api/players')
    app.register_blueprint(checkins_bp, url_prefix='/api/checkins')
    app.register_blueprint(uploads_bp, url_prefix='/api/images')
    app.register_blueprint(subgroups_bp, url_prefix='/api/subgroups')
    app.register_blueprint(matches_bp, url_prefix='/api/matches')
    app.register_blueprint(branches_bp, url_prefix='/api/branches')
    app.register_blueprint(coaches, url_prefix='/api/coaches')
    app.register_blueprint(player_payments, url_prefix='/api/players')  # Nested under /api/players
    app.register_blueprint(trainings_bp, url_prefix='/api/trainings')
    app.register_blueprint(seasons_bp, url_prefix='/api/seasons')
    app.register_blueprint(employees_bp, url_prefix='/api/employees')

    @app.route('/')
    def root():
        if _web_ready():
            return send_from_directory(web_build_dir, 'index.html')
        return jsonify({
            'message': 'Club Management API is running',
            'health': '/api/health',
            'base': '/api',
            'privacy_policy': '/privacy-policy',
            'delete_account': '/delete-account',
        })

    @app.route('/<path:path>')
    def web_app(path):
        if path.startswith('api'):
            return jsonify({'error': 'Not found'}), 404
        if _web_ready():
            file_path = os.path.join(web_build_dir, path)
            if os.path.isfile(file_path):
                return send_from_directory(web_build_dir, path)
            return send_from_directory(web_build_dir, 'index.html')
        return jsonify({'error': 'Not found'}), 404

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
        print(f"Database file: {db.engine.url}")
        _ensure_schema_updates()
        # Create superadmin if not exists
        User.create_superadmin(username='zyadw', password='ZWL@2009')
        current_season = _ensure_default_season()
        _backfill_legacy_season_ids(current_season.id if current_season else None)
        print("Database initialized and superadmin created (zyadw/ZWL@2009)")
    
    return app


# Create app instance for running directly
app = create_app()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

