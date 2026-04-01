
import os
import uuid
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import torch
from colorizer_engine import colorize_image

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'static/uploads'
RESULT_FOLDER = 'static/results'
CHECKPOINT_PATH = 'checkpoints/checkpoint_epoch_100.pth'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    # Support both 'file' (from JS) and 'image' (from HTML name)
    file = request.files.get('file') or request.files.get('image')
    
    if not file:
        return jsonify({'error': 'No image provided'}), 400
    
    if file.filename == '':
        return jsonify({'error': 'No image selected'}), 400

    file_ext = os.path.splitext(file.filename)[1]
    unique_id = str(uuid.uuid4())
    input_filename = f"{unique_id}_input{file_ext}"
    output_filename = f"{unique_id}_output.jpg"
    
    input_path = os.path.join(UPLOAD_FOLDER, input_filename)
    output_path = os.path.join(RESULT_FOLDER, output_filename)
    
    file.save(input_path)
    
    try:
        current_checkpoint = CHECKPOINT_PATH
        if not os.path.exists(CHECKPOINT_PATH):
             checkpoints = [f for f in os.listdir('checkpoints') if f.endswith('.pth')]
             if not checkpoints:
                 return jsonify({'error': 'Model checkpoint not found. Please train the model first.'}), 500
             try:
                 checkpoints.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]))
                 current_checkpoint = os.path.join('checkpoints', checkpoints[-1])
             except:
                 checkpoints.sort()
                 current_checkpoint = os.path.join('checkpoints', checkpoints[-1])

        colorize_image(input_path, current_checkpoint, output_path)
        
        return jsonify({
            'input_url': f'/static/uploads/{input_filename}',
            'output_url': f'/static/results/{output_filename}'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
