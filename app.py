# app.py - Flask based device verification API for Render
# Deploy on Render: connect GitHub repo, use "Python 3" environment, start command: gunicorn app:app

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
from datetime import datetime
import time
import re
from typing import Dict, Any

app = Flask(__name__)
CORS(app)  # Enable CORS for all origins

# Store verification sessions (in production use Redis, but this works for demo)
verification_sessions: Dict[str, Dict[str, Any]] = {}

# HTML template for the 3-stage verification interface
VERIFICATION_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes, viewport-fit=cover">
    <title>Device Verification • SecureAPI</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: linear-gradient(135deg, #0a0e1a 0%, #0f1322 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            padding: 16px;
        }

        .container {
            max-width: 500px;
            width: 100%;
            background: rgba(18, 22, 40, 0.85);
            backdrop-filter: blur(20px);
            border-radius: 48px;
            padding: 32px 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            border: 1px solid rgba(255, 255, 255, 0.1);
            transition: all 0.3s ease;
        }

        .status-card {
            text-align: center;
        }

        .icon {
            width: 80px;
            height: 80px;
            margin: 0 auto 24px;
            background: rgba(0, 200, 255, 0.1);
            border-radius: 60px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 44px;
            border: 1px solid rgba(0, 200, 255, 0.3);
        }

        .stage {
            font-size: 14px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #00c8ff;
            font-weight: 600;
            margin-bottom: 12px;
        }

        .message {
            font-size: 22px;
            font-weight: 600;
            color: white;
            margin-bottom: 16px;
            line-height: 1.3;
        }

        .sub-message {
            font-size: 14px;
            color: #8e9aaf;
            margin-bottom: 32px;
        }

        .progress-bar {
            width: 100%;
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 0;
        }

        .progress-fill {
            height: 100%;
            width: 0%;
            background: linear-gradient(90deg, #00c8ff, #0077ff);
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .loader {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(0, 200, 255, 0.3);
            border-radius: 50%;
            border-top-color: #00c8ff;
            animation: spin 0.8s linear infinite;
            margin-right: 10px;
            vertical-align: middle;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .result-box {
            background: rgba(0, 0, 0, 0.4);
            border-radius: 24px;
            padding: 20px;
            margin-top: 24px;
            text-align: left;
            border: 1px solid rgba(255, 255, 255, 0.08);
        }

        .result-line {
            font-family: 'SF Mono', 'Monaco', monospace;
            font-size: 12px;
            color: #b4c2e7;
            padding: 8px 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            word-break: break-all;
        }

        .result-line:last-child {
            border-bottom: none;
        }

        .badge {
            display: inline-block;
            background: #00c8ff20;
            color: #00c8ff;
            border-radius: 20px;
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 600;
            margin-left: 8px;
        }

        .success {
            color: #00ffaa;
        }

        .error {
            color: #ff4466;
        }

        button {
            background: linear-gradient(135deg, #0066ff, #00ccff);
            border: none;
            color: white;
            font-weight: 600;
            padding: 14px 28px;
            border-radius: 40px;
            font-size: 16px;
            cursor: pointer;
            margin-top: 24px;
            width: 100%;
            transition: transform 0.2s, opacity 0.2s;
        }

        button:hover {
            transform: scale(0.98);
            opacity: 0.9;
        }

        .hidden {
            display: none;
        }

        .json-output {
            background: #0a0e1a;
            padding: 12px;
            border-radius: 16px;
            font-family: monospace;
            font-size: 11px;
            overflow-x: auto;
            color: #8e9aaf;
            margin-top: 16px;
        }
    </style>
</head>
<body>
    <div class="container" id="app">
        <div class="status-card">
            <div class="icon" id="stageIcon">🔒</div>
            <div class="stage" id="stageLabel">STAGE 1/3</div>
            <div class="message" id="messageText">Please Wait<br>Verifying Your Device</div>
            <div class="sub-message" id="subMessage">Initializing secure handshake...</div>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            <div id="loaderContainer"><span class="loader"></span> Processing...</div>
        </div>
        <div id="resultPanel" class="result-box hidden">
            <div style="font-weight: 600; margin-bottom: 12px;">✓ VERIFICATION COMPLETE</div>
            <div id="resultContent"></div>
            <div class="json-output" id="jsonOutput"></div>
            <button id="resetBtn">⟳ Verify Again</button>
        </div>
    </div>

    <script>
        // STAGE TIMELINE (in milliseconds)
        const STAGE1_DURATION = 10000;   // 10 seconds "Please wait Verifying"
        const STAGE2_DURATION = 3000;     // "Waiting for system Safari Connection"
        const STAGE3_DURATION = 2000;     // "Safari connect Successfull"

        let currentStage = 0;
        let timeouts = [];

        // Get device info from browser
        function getDeviceData() {
            const userAgent = navigator.userAgent;
            let deviceName = "Unknown Device";
            
            // Detect device name from userAgent
            if (/iPhone/i.test(userAgent)) deviceName = "iPhone";
            else if (/iPad/i.test(userAgent)) deviceName = "iPad";
            else if (/iPod/i.test(userAgent)) deviceName = "iPod";
            else if (/Android/i.test(userAgent)) {
                const match = userAgent.match(/Android\s([\d.]+)/);
                deviceName = `Android Device ${match ? match[1] : ''}`;
            }
            else if (/Mac/i.test(userAgent)) deviceName = "Mac";
            else if (/Windows/i.test(userAgent)) deviceName = "Windows PC";
            else if (/Linux/i.test(userAgent)) deviceName = "Linux Device";
            else deviceName = "Generic Device";
            
            const isIOS = /iPad|iPhone|iPod|Macintosh/.test(userAgent) && !window.MSStream;
            const isApple = /Mac|iPhone|iPad|iPod/.test(userAgent);
            
            // Extract Sec-Fetch-Dest from headers (client-side simulation)
            // In real scenario it's sent by browser; we'll simulate based on navigation type
            let secFetchDest = "document";
            if (window.location.href.includes("api")) secFetchDest = "empty";
            
            return {
                deviceName: deviceName,
                userAgent: userAgent,
                isIOS: isIOS,
                isApple: isApple,
                platform: navigator.platform,
                language: navigator.language,
                secFetchDest: secFetchDest,
                timestamp: new Date().toISOString()
            };
        }

        async function sendToAPI(deviceInfo) {
            try {
                const response = await fetch('/api/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(deviceInfo)
                });
                return await response.json();
            } catch (err) {
                console.error("API error:", err);
                return { error: "API unreachable, but showing client data" };
            }
        }

        function clearTimeouts() {
            timeouts.forEach(t => clearTimeout(t));
            timeouts = [];
        }

        function updateUI(stage, progressPercent, mainMsg, subMsg, iconEmoji) {
            const stageLabel = document.getElementById('stageLabel');
            const messageText = document.getElementById('messageText');
            const subMessage = document.getElementById('subMessage');
            const progressFill = document.getElementById('progressFill');
            const stageIcon = document.getElementById('stageIcon');
            
            stageLabel.innerText = `STAGE ${stage}/3`;
            messageText.innerHTML = mainMsg;
            subMessage.innerText = subMsg;
            progressFill.style.width = `${progressPercent}%`;
            stageIcon.innerText = iconEmoji;
        }

        function showResult(deviceInfo, apiResponse) {
            // Hide status area loader
            document.getElementById('loaderContainer').classList.add('hidden');
            document.querySelector('.progress-bar').style.display = 'none';
            
            const resultPanel = document.getElementById('resultPanel');
            const resultContent = document.getElementById('resultContent');
            const jsonOutput = document.getElementById('jsonOutput');
            
            // Build display content
            const isIOS = deviceInfo.isIOS || deviceInfo.isApple;
            let supportMessage = "";
            let supportClass = "";
            
            if (isIOS) {
                supportMessage = "✅ This Device support Module 37.7vz<br>Cashout Df -fd Sec-Fetch-Dest: " + deviceInfo.secFetchDest;
                supportClass = "success";
            } else {
                supportMessage = "❌ This device does NOT support iOS Module 37.7vz<br>⚠️ Android / other OS: supports only iOS";
                supportClass = "error";
            }
            
            resultContent.innerHTML = `
                <div class="result-line"><strong>🖥️ Your device name:</strong> ${deviceInfo.deviceName}</div>
                <div class="result-line"><strong>🔍 User agent name:</strong> ${escapeHtml(deviceInfo.userAgent)}</div>
                <div class="result-line"><strong>📱 Platform:</strong> ${deviceInfo.platform}</div>
                <div class="result-line"><strong class="${supportClass}">${supportMessage}</strong></div>
                <div class="result-line"><strong>✅ Device Successfully Checked</strong> <span style="color:#00ffaa;">✔️</span></div>
            `;
            
            // JSON output
            const fullJson = {
                status: "completed",
                device: {
                    deviceName: deviceInfo.deviceName,
                    userAgent: deviceInfo.userAgent,
                    isIOS: deviceInfo.isIOS,
                    isApple: deviceInfo.isApple,
                    platform: deviceInfo.platform,
                    secFetchDest: deviceInfo.secFetchDest
                },
                support: isIOS ? "Module 37.7vz enabled" : "iOS required (not supported)",
                message: isIOS ? "This Device support Module 37.7vz. Cashout Df -fd Sec-Fetch-Dest" : "Android / non-Apple: supports only iOS",
                timestamp: deviceInfo.timestamp,
                apiResponse: apiResponse
            };
            
            jsonOutput.innerText = JSON.stringify(fullJson, null, 2);
            resultPanel.classList.remove('hidden');
        }

        function escapeHtml(str) {
            return str.replace(/[&<>]/g, function(m) {
                if (m === '&') return '&amp;';
                if (m === '<') return '&lt;';
                if (m === '>') return '&gt;';
                return m;
            });
        }

        async function startVerification() {
            clearTimeouts();
            currentStage = 0;
            document.getElementById('resultPanel').classList.add('hidden');
            document.getElementById('loaderContainer').classList.remove('hidden');
            document.querySelector('.progress-bar').style.display = 'block';
            
            // Stage 1: 10 seconds - Please Wait Verifying Your Device
            updateUI(1, 0, "Please Wait<br>Verifying Your Device", "Initializing secure environment...", "⏳");
            let startTime = Date.now();
            
            await new Promise(resolve => {
                const interval = setInterval(() => {
                    const elapsed = Date.now() - startTime;
                    const percent = Math.min(100, (elapsed / STAGE1_DURATION) * 100);
                    document.getElementById('progressFill').style.width = `${percent}%`;
                    if (elapsed >= STAGE1_DURATION) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 50);
                const timeoutId = setTimeout(() => {}, STAGE1_DURATION);
                timeouts.push(timeoutId);
            });
            
            // Stage 2: Waiting for system Safari Connection
            updateUI(2, 0, "Waiting for system<br>Safari Connection", "Establishing secure tunnel...", "🌐");
            startTime = Date.now();
            await new Promise(resolve => {
                const interval = setInterval(() => {
                    const elapsed = Date.now() - startTime;
                    const percent = Math.min(100, (elapsed / STAGE2_DURATION) * 100);
                    document.getElementById('progressFill').style.width = `${percent}%`;
                    if (elapsed >= STAGE2_DURATION) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 50);
                const timeoutId = setTimeout(() => {}, STAGE2_DURATION);
                timeouts.push(timeoutId);
            });
            
            // Stage 3: Safari connect Successful
            updateUI(3, 0, "Safari connect<br>Successful", "Handshake verified, fetching device identity", "🔓");
            startTime = Date.now();
            await new Promise(resolve => {
                const interval = setInterval(() => {
                    const elapsed = Date.now() - startTime;
                    const percent = Math.min(100, (elapsed / STAGE3_DURATION) * 100);
                    document.getElementById('progressFill').style.width = `${percent}%`;
                    if (elapsed >= STAGE3_DURATION) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 50);
                const timeoutId = setTimeout(() => {}, STAGE3_DURATION);
                timeouts.push(timeoutId);
            });
            
            // Get device data & send to API backend
            const deviceInfo = getDeviceData();
            const apiResult = await sendToAPI(deviceInfo);
            showResult(deviceInfo, apiResult);
        }

        document.getElementById('resetBtn')?.addEventListener('click', () => {
            location.reload(); // simple reset
        });

        // start on load
        window.addEventListener('load', () => {
            startVerification();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    """Serve the verification interface"""
    return render_template_string(VERIFICATION_PAGE)

@app.route('/api/verify', methods=['POST'])
def verify_device():
    """
    API endpoint that receives device data and returns JSON response.
    Implements logic: if iOS/Apple => support Module 37.7vz, else => supports only iOS
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_agent = data.get('userAgent', '')
        device_name = data.get('deviceName', 'Unknown')
        is_ios = data.get('isIOS', False)
        is_apple = data.get('isApple', False)
        sec_fetch_dest = data.get('secFetchDest', 'document')
        
        # Determine if device supports iOS Module
        supports_ios_module = is_ios or is_apple
        
        # Build response as per requirement
        if supports_ios_module:
            response_data = {
                "status": "success",
                "message": "This Device support Module 37.7vz",
                "cashout_info": f"Cashout Df -fd Sec-Fetch-Dest: {sec_fetch_dest}",
                "device": {
                    "deviceName": device_name,
                    "userAgent": user_agent,
                    "platform": data.get('platform', 'unknown'),
                    "support_module": "37.7vz"
                },
                "verification": "Device Successfully Checked",
                "ios_only_note": null
            }
        else:
            response_data = {
                "status": "blocked",
                "message": "iOS required: supports only iOS",
                "cashout_info": None,
                "device": {
                    "deviceName": device_name,
                    "userAgent": user_agent,
                    "platform": data.get('platform', 'unknown')
                },
                "verification": "Device Successfully Checked — but OS not supported",
                "ios_only_note": "This endpoint supports only iOS / Apple devices. Android or others are rejected."
            }
        
        # Add extra details
        response_data["timestamp"] = datetime.utcnow().isoformat()
        response_data["sec-fetch-dest"] = sec_fetch_dest
        
        return jsonify(response_data), 200
    
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render"""
    return jsonify({
        "status": "active",
        "service": "Device Verification API",
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/api/device-info', methods=['GET'])
def device_info_demo():
    """
    Alternative GET endpoint to demonstrate raw device detection from request headers
    Useful for testing on Render directly
    """
    user_agent = request.headers.get('User-Agent', 'unknown')
    sec_fetch_dest = request.headers.get('Sec-Fetch-Dest', 'not_provided')
    
    # Basic detection
    is_ios = bool(re.search(r'iPhone|iPad|iPod|Macintosh', user_agent)) and 'like Mac' not in user_agent
    is_apple_device = bool(re.search(r'iPhone|iPad|iPod|Mac', user_agent))
    
    if 'Android' in user_agent:
        device_type = "Android"
    elif is_ios or is_apple_device:
        device_type = "iOS/Apple"
    else:
        device_type = "Other"
    
    return jsonify({
        "endpoint": "GET /api/device-info",
        "detected_device_type": device_type,
        "user_agent": user_agent,
        "sec_fetch_dest": sec_fetch_dest,
        "supports_ios_module": is_ios or is_apple_device,
        "message": "This Device support Module 37.7vz" if (is_ios or is_apple_device) else "supports only iOS",
        "cashout_df": f"-fd {sec_fetch_dest}" if (is_ios or is_apple_device) else None,
        "verification": "Device Successfully Checked"
    })

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found", "available": ["/", "/api/verify", "/api/health", "/api/device-info"]}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error", "status": "failed"}), 500

# For local testing (Render uses gunicorn)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=False)
