from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from monitor import NetworkMonitor
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configure Gemini
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    model = None
    print('Warning: GEMINI_API_KEY is not set. AI insights will use fallback text.')

monitor = NetworkMonitor()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/scan', methods=['POST'])
def scan():
    """Perform a network performance scan"""
    data = request.json
    target = data.get('target')
    
    if not target:
        return jsonify({
            'success': False,
            'error': 'Please enter a target (IP address or hostname)'
        })
    
    try:
        target = target.strip()

        # Ping the target
        result = monitor.ping_target(target, count=10)
        
        # Get AI insights
        ai_insights = get_ai_insights(target, result)
        
        return jsonify({
            'success': True,
            'target': target,
            'metrics': result,
            'ai_insights': ai_insights
        })
    except ValueError as ve:
        return jsonify({
            'success': False,
            'error': str(ve)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to reach {target}: {str(e)}'
        })

def get_ai_insights(target, metrics):
    """Get AI-powered insights about network performance"""
    target_type = metrics.get('target_type', 'network')
    prompt = f"""
Network Performance Test Results:
Target: {target}
Target type: {target_type}
Average Latency: {metrics['avg_latency']} ms
Minimum Latency: {metrics.get('min_latency', 'N/A')} ms
Maximum Latency: {metrics.get('max_latency', 'N/A')} ms
Jitter: {metrics['jitter']} ms
Packet Loss: {metrics['packet_loss']}%
Success Rate: {metrics['success_rate']}%

For a healthy local network, latency should be 1-10ms with 0% packet loss.
For internet targets, latency typically ranges from 20-80ms.

Analyze this network performance data and provide:
1. Overall health assessment
2. Any issues detected (high latency, packet loss, jitter)
3. Recommended actions to improve network health

Return a short paragraph.
"""
    
    if model is None:
        return (
            f"No AI key available. Network result for {target}: "
            f"{metrics['avg_latency']} ms latency, {metrics['jitter']} ms jitter, "
            f"{metrics['packet_loss']}% packet loss."
        )

    try:
        response = model.generate_content(prompt)
        return getattr(response, 'text', str(response))
    except Exception as e:
        print(f"AI error: {e}")
        return (
            f"Target: {target} | Latency: {metrics['avg_latency']} ms | "
            f"Loss: {metrics['packet_loss']}% | Jitter: {metrics['jitter']} ms"
        )

if __name__ == '__main__':
    print("\n" + "="*50)
    print("📊 Network Performance Analyzer")
    print("="*50)
    print("📍 Running on: http://localhost:5006")
    print("="*50 + "\n")
    app.run(debug=True, port=5006)