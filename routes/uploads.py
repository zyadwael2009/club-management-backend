import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory, current_app
from werkzeug.utils import secure_filename

uploads_bp = Blueprint('uploads', __name__)


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


@uploads_bp.route('', methods=['POST'])
def upload_file():
    """Upload an image file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    
    # Generate unique filename
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{uuid.uuid4()}.{ext}"
    
    # Ensure upload directory exists
    upload_folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(upload_folder, exist_ok=True)
    
    # Save file
    filepath = os.path.join(upload_folder, filename)
    file.save(filepath)
    
    # Return the URL to access the file
    file_url = f"/api/images/{filename}"
    
    return jsonify({
        'url': file_url,
        'filename': filename,
    }), 201


@uploads_bp.route('/<filename>', methods=['GET'])
def get_image(filename):
    """Serve an uploaded image"""
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@uploads_bp.route('/<filename>', methods=['DELETE'])
def delete_image(filename):
    """Delete an uploaded image"""
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({'message': 'Image deleted successfully'})
    
    return jsonify({'error': 'Image not found'}), 404
