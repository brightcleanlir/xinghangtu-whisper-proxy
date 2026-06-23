#!/usr/bin/env python3
"""
Whisper 语音识别代理服务器 - Railway 部署版
- 使用环境变量 OPENAI_API_KEY（不在代码中硬编码）
- 使用 Flask + gunicorn（生产级）
- 支持 CORS（跨域请求）
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 允许跨域

# 从环境变量读取（Railway 后台配置）
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'whisper-1')
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'service': 'whisper-proxy',
        'has_api_key': bool(OPENAI_API_KEY),
        'model': WHISPER_MODEL
    })

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """转录音频（接收文件上传）"""
    try:
        # 检查 API 密钥
        if not OPENAI_API_KEY:
            return jsonify({
                'success': False,
                'error': '未配置 OPENAI_API_KEY 环境变量（请在 Railway 后台配置）'
            }), 500
        
        # 检查是否有文件
        if 'audio' not in request.files:
            return jsonify({
                'success': False,
                'error': '未收到音频文件'
            }), 400
        
        audio_file = request.files['audio']
        
        # 检查文件大小
        audio_file.seek(0, 2)
        file_size = audio_file.tell()
        audio_file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({
                'success': False,
                'error': f'文件过大（最大25MB，当前{file_size/1024/1024:.1f}MB）'
            }), 400
        
        # 调用 Whisper API
        print(f"🎤 正在调用 Whisper API（文件大小: {file_size/1024:.1f}KB）...")
        
        # 读取文件数据
        file_data = audio_file.read()
        
        # 构建 multipart/form-data
        boundary = b'----WhisperRailwayBoundary'
        body = b''
        
        # 添加 model 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += WHISPER_MODEL.encode() + b'\r\n'
        
        # 添加 language 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += b'zh\r\n'
        
        # 添加 file 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
        body += b'Content-Type: audio/webm\r\n\r\n'
        body += file_data + b'\r\n'
        
        # 结束边界
        body += b'--' + boundary + b'--\r\n'
        
        # 发送请求
        url = 'https://api.openai.com/v1/audio/transcriptions'
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            transcript = result.get('text', '')
            
            print(f"✅ 识别成功: {transcript[:50]}...")
            
            return jsonify({
                'success': True,
                'transcript': transcript,
                'language': 'zh',
                'model': WHISPER_MODEL
            })
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ Whisper API 错误: {e.code} - {error_body}")
        return jsonify({
            'success': False,
            'error': f'Whisper API 错误: {e.code} - {error_body}'
        }), e.code
        
    except Exception as e:
        print(f"❌ 服务器错误: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/transcribe-base64', methods=['POST'])
def transcribe_base64():
    """转录 Base64 编码的音频"""
    try:
        # 检查 API 密钥
        if not OPENAI_API_KEY:
            return jsonify({
                'success': False,
                'error': '未配置 OPENAI_API_KEY 环境变量'
            }), 500
        
        # 解析请求
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({
                'success': False,
                'error': '缺少 audio 字段'
            }), 400
        
        # 解码 Base64 音频
        audio_base64 = data['audio']
        audio_bytes = base64.b64decode(audio_base64)
        
        # 检查大小
        if len(audio_bytes) > MAX_FILE_SIZE:
            return jsonify({
                'success': False,
                'error': f'音频数据过大（最大25MB）'
            }), 400
        
        print(f"🎤 正在调用 Whisper API（Base64 解码后: {len(audio_bytes)/1024:.1f}KB）...")
        
        # 调用 Whisper API
        boundary = b'----WhisperRailwayBoundary'
        body = b''
        
        # 添加 model 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += WHISPER_MODEL.encode() + b'\r\n'
        
        # 添加 language 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += b'zh\r\n'
        
        # 添加 file 字段
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
        body += b'Content-Type: audio/webm\r\n\r\n'
        body += audio_bytes + b'\r\n'
        
        # 结束边界
        body += b'--' + boundary + b'--\r\n'
        
        # 发送请求
        url = 'https://api.openai.com/v1/audio/transcriptions'
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Authorization': f'Bearer {OPENAI_API_KEY}',
                'Content-Type': f'multipart/form-data; boundary={boundary.decode()}'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            transcript = result.get('text', '')
            
            print(f"✅ 识别成功: {transcript[:50]}...")
            
            return jsonify({
                'success': True,
                'transcript': transcript,
                'language': 'zh',
                'model': WHISPER_MODEL
            })
            
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"❌ Whisper API 错误: {e.code} - {error_body}")
        return jsonify({
            'success': False,
            'error': f'Whisper API 错误: {e.code} - {error_body}'
        }), e.code
        
    except Exception as e:
        print(f"❌ 服务器错误: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # 本地测试用
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
