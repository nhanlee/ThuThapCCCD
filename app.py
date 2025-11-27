import os
import json
import base64
import logging
import zipfile
import pandas as pd
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, send_file
from werkzeug.utils import secure_filename
import io
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = 'images'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Đảm bảo thư mục upload tồn tại
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Thông tin kết nối MySQL từ Railway
DB_CONFIG = {
    'host': 'metro.proxy.rlwy.net',
    'port': 56134,
    'user': 'root',
    'password': 'hYlXTSpFIELiFCpPIpdlklknNdOEDlno',
    'database': 'railway'
}

def get_db_connection():
    """Tạo kết nối đến MySQL database"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        logger.error(f"Lỗi kết nối MySQL: {e}")
        return None

# Khởi tạo database - kiểm tra kết nối
def init_db():
    try:
        conn = get_db_connection()
        if conn:
            logger.info("Kết nối MySQL thành công!")
            conn.close()
        else:
            logger.error("Không thể kết nối đến MySQL database")
    except Exception as e:
        logger.error(f"Lỗi khởi tạo database: {e}")

init_db()

# Khởi tạo YOLO model (có xử lý lỗi)
face_model = None
try:
    from ultralytics import YOLO
    logger.info("Đang tải YOLO model...")
    face_model = YOLO('yolov8n.pt')
    logger.info("YOLO model đã tải thành công")
except Exception as e:
    logger.warning(f"Không thể tải YOLO model: {e}")
    logger.warning("Ứng dụng sẽ chạy mà không có nhận diện khuôn mặt")

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

        # Lưu ảnh mặt trước và mặt sau
        front_filename = save_image(data.get('front'), cccd_number + '_front.jpg') if data.get('front') else None
        back_filename = save_image(data.get('back'), cccd_number + '_back.jpg') if data.get('back') else None
        
        # Tự động nhận diện và cắt khuôn mặt từ ảnh mặt trước
        face_filename = None
        face_detected = False
        
        if data.get('front') and face_model:
            try:
                face_base64 = detect_and_crop_face(data.get('front'))
                if face_base64:
                    face_filename = save_image(face_base64, cccd_number + '_face.jpg')
                    face_detected = True
                    logger.info(f"Đã nhận diện và cắt khuôn mặt thành công cho CCCD: {cccd_number}")
                else:
                    logger.info(f"Không tìm thấy khuôn mặt trong ảnh CCCD: {cccd_number}")
            except Exception as e:
                logger.error(f"Lỗi khi nhận diện khuôn mặt: {e}")

        # Lưu vào database MySQL
        conn = get_db_connection()
        if conn is None:
            return jsonify({
                'success': False,
                'error': 'database_error',
                'message': 'Không thể kết nối đến cơ sở dữ liệu'
            }), 500

        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO customer 
            (timestamp, cccd, cmnd_cu, hoten, gioitinh, ngaysinh, diachi, ngaycap, front_image, back_image, face_image, nguoi_thuc_hien)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            'User'  # nguoi_thuc_hien
        ))
        
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Lưu thành công!',
            'cccd': cccd_number,
            'face_detected': face_detected,
            'ai_enabled': face_model is not None
        })

    except Exception as e:
        logger.error(f"Lỗi server: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': f'Lỗi server: {str(e)}'
        }), 500

def detect_and_crop_face(base64_data):
    """Nhận diện và cắt khuôn mặt từ ảnh sử dụng YOLOv8"""
    if not face_model:
        return None
        
    try:
        import cv2
        import numpy as np
        
        # Chuyển base64 thành image
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',')[1]
        
        image_data = base64.b64decode(base64_data)
        nparr = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            logger.error("Không thể decode ảnh")
            return None
        
        # Nhận diện khuôn mặt với YOLOv8
        results = face_model(img, verbose=False)
        
        # Tìm khuôn mặt có độ tin cậy cao nhất
        best_face = None
        best_conf = 0
        
        for result in results:
            boxes = result.boxes
            if boxes is not None and len(boxes) > 0:
                for box in boxes:
                    conf = box.conf.item()
                    # Lấy tất cả các vật thể được detect (có thể là khuôn mặt, người, etc.)
                    if conf > 0.5 and conf > best_conf:
                        best_conf = conf
                        best_face = box.xyxy[0].cpu().numpy()
        
        if best_face is not None:
            logger.info(f"Tìm thấy khuôn mặt với độ tin cậy: {best_conf:.2f}")
            
            # Cắt khuôn mặt
            x1, y1, x2, y2 = map(int, best_face)
            
            # Mở rộng vùng cắt một chút
            margin = 0.1
            h, w = img.shape[:2]
            x1 = max(0, int(x1 - (x2 - x1) * margin))
            y1 = max(0, int(y1 - (y2 - y1) * margin))
            x2 = min(w, int(x2 + (x2 - x1) * margin))
            y2 = min(h, int(y2 + (y2 - y1) * margin))
            
            face_crop = img[y1:y2, x1:x2]
            
            if face_crop.size == 0:
                return None
                
            # Chuyển về base64
            success, encoded_image = cv2.imencode('.jpg', face_crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if success:
                face_base64 = base64.b64encode(encoded_image).decode('utf-8')
                return f"data:image/jpeg;base64,{face_base64}"
        
        logger.info("Không tìm thấy khuôn mặt trong ảnh")
        return None
        
    except Exception as e:
        logger.error(f"Lỗi trong detect_and_crop_face: {e}")
        return None

@app.route('/checkDuplicate', methods=['POST'])
def check_duplicate():
    try:
        data = request.get_json()
        cccd_number = str(data.get('cccd', '')).strip()
        
        is_duplicate = check_duplicate_cccd(cccd_number)
        
        return jsonify({'duplicate': is_duplicate})
    
    except Exception as e:
        logger.error(f"Lỗi kiểm tra trùng: {str(e)}")
        return jsonify({'duplicate': False})

@app.route('/testConnection', methods=['GET'])
def test_connection():
    try:
        # Kiểm tra kết nối database
        conn = get_db_connection()
        if conn is None:
            return jsonify({
                'status': 'error',
                'message': 'Không thể kết nối đến MySQL database',
                'sheetName': 'customer',
                'sheetId': 'mysql_database'
            }), 500
            
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM customer')
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        # Kiểm tra model YOLO
        model_status = "loaded" if face_model else "not_loaded"
        
        return jsonify({
            'status': 'ok',
            'sheetExists': True,
            'folderExists': True,
            'modelStatus': model_status,
            'aiEnabled': face_model is not None,
            'sheetName': 'customer',
            'sheetId': 'mysql_database',
            'recordCount': count
        })
    
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'sheetName': 'customer',
            'sheetId': 'mysql_database'
        }), 500

def check_duplicate_cccd(cccd_number):
    """Kiểm tra CCCD có trùng không"""
    try:
        conn = get_db_connection()
        if conn is None:
            return False

        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM customer WHERE cccd = %s', (cccd_number,))
        count = cursor.fetchone()[0]
        
        cursor.close()
        conn.close()
        return count > 0
    
    except Exception as e:
        logger.error(f"Lỗi kiểm tra trùng CCCD: {str(e)}")
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
        logger.error(f"Lỗi lưu ảnh: {str(e)}")
        return None

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/health')
def health_check():
    conn = get_db_connection()
    db_status = 'connected' if conn else 'disconnected'
    if conn:
        conn.close()
    
    return jsonify({
        'status': 'healthy', 
        'ai_enabled': face_model is not None,
        'database': db_status
    })

# Thêm endpoint mới để lấy danh sách CCCD đã quét
@app.route('/getCCCDList', methods=['GET'])
def get_cccd_list():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({
                'success': False,
                'error': 'database_error',
                'message': 'Không thể kết nối đến cơ sở dữ liệu'
            }), 500

        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT ID, timestamp, cccd, cmnd_cu, hoten, gioitinh, ngaysinh, 
                   diachi, ngaycap, front_image, back_image, face_image
            FROM customer 
            ORDER BY timestamp DESC
        ''')
        
        records = cursor.fetchall()
        cursor.close()
        conn.close()

        cccd_list = []
        for record in records:
            cccd_list.append({
                'id': record[0],
                'timestamp': record[1],
                'cccd': record[2],
                'cmnd_cu': record[3],
                'hoten': record[4],
                'gioitinh': record[5],
                'ngaysinh': record[6],
                'diachi': record[7],
                'ngaycap': record[8],
                'front_image': record[9],
                'back_image': record[10],
                'face_image': record[11]
            })

        return jsonify({
            'success': True,
            'records': cccd_list
        })
    
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách CCCD: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'server_error',
            'message': f'Lỗi server: {str(e)}'
        }), 500

# Thêm endpoint để export dữ liệu ra Excel
@app.route('/exportExcel')
def export_excel():
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({
                'success': False,
                'error': 'database_error',
                'message': 'Không thể kết nối đến cơ sở dữ liệu'
            }), 500
        
        # Đọc dữ liệu từ database
        df = pd.read_sql_query('''
            SELECT timestamp, cccd, cmnd_cu, hoten, gioitinh, ngaysinh, 
                   diachi, ngaycap, front_image, back_image, face_image
            FROM customer 
            ORDER BY timestamp DESC
        ''', conn)
        
        conn.close()
        
        # Tạo file Excel trong memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='CCCD_Records', index=False)
        
        output.seek(0)
        
        # Tạo tên file với timestamp
        filename = f"cccd_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        logger.error(f"Lỗi khi export Excel: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'export_error',
            'message': f'Lỗi khi export Excel: {str(e)}'
        }), 500

# Thêm endpoint để export ảnh ra file ZIP
@app.route('/exportImages')
def export_images():
    try:
        # Lấy danh sách tất cả file ảnh trong thư mục upload
        image_files = []
        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                image_files.append(filename)
        
        if not image_files:
            return jsonify({
                'success': False,
                'error': 'no_images',
                'message': 'Không có ảnh nào để export'
            }), 404
        
        # Tạo file ZIP trong memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for filename in image_files:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                zip_file.write(file_path, filename)
        
        zip_buffer.seek(0)
        
        # Tạo tên file với timestamp
        filename = f"cccd_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        logger.error(f"Lỗi khi export images: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'export_error',
            'message': f'Lỗi khi export images: {str(e)}'
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)