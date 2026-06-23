#!/usr/bin/env python3
"""
Whisper speech recognition proxy server - Railway deployment
- Environment variable GOOGLE_API_KEY (NOT hardcoded)
- Flask + gunicorn
- CORS support
- ASCII-only print statements (avoids latin-1 encoding issues on Railway)
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
from flask import Flask, request, jsonify
from flask_cors import CORS

# Force UTF-8 everywhere
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

app = Flask(__name__)
CORS(app)  # Allow cross-origin

# Read from environment variables (configured in Railway dashboard)
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
GOOGLE_SITE_VERIFICATION = os.getenv('GOOGLE_SITE_VERIFICATION', '')
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'whisper-1')
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'service': 'whisper-proxy',
        'has_api_key': bool(GOOGLE_API_KEY) or bool(GOOGLE_SITE_VERIFICATION),
        'model': WHISPER_MODEL
    })

@app.route('/transcribe', methods=['POST'])
def transcribe_audio():
    """Transcribe audio from file upload"""
    try:
        # Use GOOGLE_API_KEY first, fall back to GOOGLE_SITE_VERIFICATION
        api_key = GOOGLE_API_KEY or GOOGLE_SITE_VERIFICATION or ''
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key not configured (set GOOGLE_API_KEY in Railway Variables)'
            }), 500

        # Check if file was uploaded
        if 'audio' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No audio file received'
            }), 400

        audio_file = request.files['audio']

        # Check file size
        audio_file.seek(0, 2)
        file_size = audio_file.tell()
        audio_file.seek(0)

        if file_size > MAX_FILE_SIZE:
            return jsonify({
                'success': False,
                'error': 'File too large (max 25MB, current {:.1f}MB)'.format(file_size / 1024 / 1024)
            }), 400

        print("Calling Whisper API (file size: {:.1f}KB)...".format(file_size / 1024))

        # Read file data
        file_data = audio_file.read()

        # Build multipart/form-data
        boundary = b'----WhisperRailwayBoundary'
        body = b''

        # Add model field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += WHISPER_MODEL.encode() + b'\r\n'

        # Add language field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += b'zh\r\n'

        # Add file field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
        body += b'Content-Type: audio/webm\r\n\r\n'
        body += file_data + b'\r\n'

        # End boundary
        body += b'--' + boundary + b'--\r\n'

        # Send request to OpenAI
        url = 'https://api.openai.com/v1/audio/transcriptions'
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Authorization': 'Bearer {}'.format(api_key),
                'Content-Type': 'multipart/form-data; boundary=' + boundary.decode()
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            transcript = result.get('text', '')

            print("Transcription success: {}".format(transcript[:80]))

            return jsonify({
                'success': True,
                'transcript': transcript,
                'language': 'zh',
                'model': WHISPER_MODEL
            })

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print("Whisper API error: {} - {}".format(e.code, error_body[:200]))
        return jsonify({
            'success': False,
            'error': 'Whisper API error: {} - {}'.format(e.code, error_body)
        }), e.code

    except Exception as e:
        print("Server error: {}".format(str(e)[:200]))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/transcribe-base64', methods=['POST'])
def transcribe_base64():
    """Transcribe base64-encoded audio"""
    try:
        api_key = GOOGLE_API_KEY or GOOGLE_SITE_VERIFICATION or ''
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key not configured'
            }), 500

        # Parse request
        data = request.json
        if not data or 'audio' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing audio field'
            }), 400

        # Decode base64 audio
        audio_base64 = data['audio']
        audio_bytes = base64.b64decode(audio_base64)

        # Check size
        if len(audio_bytes) > MAX_FILE_SIZE:
            return jsonify({
                'success': False,
                'error': 'Audio data too large (max 25MB)'
            }), 400

        print("Calling Whisper API (base64 decoded: {:.1f}KB)...".format(len(audio_bytes) / 1024))

        # Build multipart/form-data
        boundary = b'----WhisperRailwayBoundary'
        body = b''

        # Add model field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += WHISPER_MODEL.encode() + b'\r\n'

        # Add language field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += b'zh\r\n'

        # Add file field
        body += b'--' + boundary + b'\r\n'
        body += b'Content-Disposition: form-data; name="file"; filename="audio.webm"\r\n'
        body += b'Content-Type: audio/webm\r\n\r\n'
        body += audio_bytes + b'\r\n'

        # End boundary
        body += b'--' + boundary + b'--\r\n'

        # Send request to OpenAI
        url = 'https://api.openai.com/v1/audio/transcriptions'
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                'Authorization': 'Bearer {}'.format(api_key),
                'Content-Type': 'multipart/form-data; boundary=' + boundary.decode()
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            transcript = result.get('text', '')

            print("Transcription success: {}".format(transcript[:80]))

            return jsonify({
                'success': True,
                'transcript': transcript,
                'language': 'zh',
                'model': WHISPER_MODEL
            })

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print("Whisper API error: {} - {}".format(e.code, error_body[:200]))
        return jsonify({
            'success': False,
            'error': 'Whisper API error: {} - {}'.format(e.code, error_body)
        }), e.code

    except Exception as e:
        print("Server error: {}".format(str(e)[:200]))
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Local testing only
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
