import os
import json
import base64
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Đảm bảo thư mục upload tồn tại
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Khởi tạo database
def init_db():
    conn = sqlite3.connect('cccd.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cccd_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            cccd TEXT UNIQUE,
            cmnd_cu TEXT,
            hoten TEXT,
            gioitinh TEXT,
            ngaysinh TEXT,
            diachi TEXT,
            ngaycap TEXT,
            front_image TEXT,
            back_image TEXT,
            face_image TEXT,
            nguoi_thuc_hien TEXT,
            email_nguoi_thuc_hien TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/saveCCCD', methods=['POST'])
def save_cccd():
    try:
        data = request.get_json()
        
        if not data or 'cccd' not in data:
            return jsonify({
                'success': False,
                'error': 'missing_cccd',
                'message': 'Thiếu số CCCD'
            }), 400

        cccd_number = str(data['cccd']).strip()
        
        # Kiểm tra trùng CCCD
        if check_duplicate_cccd(cccd_number):
            return jsonify({
                'success': False,
                'error': 'duplicate',
                'message': f'Số CCCD {cccd_number} đã tồn tại trong hệ thống!',
                'duplicateCCCD': cccd_number
            }), 400

        # Lưu ảnh
        front_filename = save_image(data.get('front'), cccd_number + '_front.jpg') if data.get('front') else None
        back_filename = save_image(data.get('back'), cccd_number + '_back.jpg') if data.get('back') else None
        face_filename = save_image(data.get('face'), cccd_number + '_face.jpg') if data.get('face') else None

        # Lưu vào database
        conn = sqlite3.connect('cccd.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO cccd_records 
            (timestamp, cccd, cmnd_cu, hoten, gioitinh, ngaysinh, diachi, ngaycap, front_image, back_image, face_image, nguoi_thuc_hien, email_nguoi_thuc_hien)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            cccd_number,
            data.get('cmnd_cu', ''),
            data.get('hoten', ''),
            data.get('gioitinh', ''),
            data.get('ngaysinh', ''),
            data.get('diachi', ''),
            data.get('ngaycap', ''),
            front_filename,
            back_filename,
            face_filename,
            'User',  # Trong thực tế, lấy từ session/login
            'user@example.com'  # Trong thực tế, lấy từ session/login
        ))
        
        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Lưu thành công!',
            'cccd': cccd_number
        })

    except Exception as e:
        print(f"Lỗi server: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': f'Lỗi server: {str(e)}'
        }), 500

@app.route('/checkDuplicate', methods=['POST'])
def check_duplicate():
    try:
        data = request.get_json()
        cccd_number = str(data.get('cccd', '')).strip()
        
        is_duplicate = check_duplicate_cccd(cccd_number)
        
        return jsonify({'duplicate': is_duplicate})
    
    except Exception as e:
        print(f"Lỗi kiểm tra trùng: {str(e)}")
        return jsonify({'duplicate': False})

@app.route('/testConnection', methods=['GET'])
def test_connection():
    try:
        # Kiểm tra kết nối database
        conn = sqlite3.connect('cccd.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM cccd_records')
        conn.close()
        
        return jsonify({
            'status': 'ok',
            'sheetExists': True,
            'folderExists': True,
            'sheetName': 'DATA',
            'sheetId': 'sqlite_database'
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'sheetName': 'DATA',
            'sheetId': 'sqlite_database'
        }), 500

def check_duplicate_cccd(cccd_number):
    """Kiểm tra CCCD có trùng không"""
    try:
        conn = sqlite3.connect('cccd.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM cccd_records WHERE cccd = ?', (cccd_number,))
        count = cursor.fetchone()[0]
        
        conn.close()
        return count > 0
    
    except Exception as e:
        print(f"Lỗi kiểm tra trùng CCCD: {str(e)}")
        return False

def save_image(base64_data, filename):
    """Lưu ảnh base64 thành file"""
    try:
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',')[1]
        
        image_data = base64.b64decode(base64_data)
        
        # Tạo tên file an toàn
        safe_filename = secure_filename(filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        return safe_filename
    
    except Exception as e:
        print(f"Lỗi lưu ảnh: {str(e)}")
        return None

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)