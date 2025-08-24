import requests
import json
import time
import argparse

class STTClient:
    def __init__(self, stt_server_url="http://localhost:5002"):
        """Initialize STT client"""
        self.stt_server_url = stt_server_url.rstrip('/')
        print(f"🔗 STT Client connecting to: {self.stt_server_url}")
    
    def check_health(self):
        """Check if STT server is healthy"""
        try:
            response = requests.get(f"{self.stt_server_url}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ STT Server is healthy")
                print(f"   Recording: {data.get('recording', False)}")
                return True
            else:
                print(f"❌ STT Server unhealthy: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to STT server: {e}")
            return False
    
    def get_status(self):
        """Get STT server status"""
        try:
            response = requests.get(f"{self.stt_server_url}/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"📊 STT Server Status:")
                print(f"   Recording: {data.get('recording', False)}")
                print(f"   Model: {data.get('model', 'unknown')}")
                print(f"   Language: {data.get('language', 'unknown')}")
                print(f"   CSV Analytics URL: {data.get('csv_analytics_url', 'unknown')}")
                return data
            else:
                print(f"❌ Failed to get status: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Error getting status: {e}")
            return None
    
    def start_recording(self):
        """Start recording on STT server"""
        try:
            print("🎤 Starting recording...")
            response = requests.post(f"{self.stt_server_url}/start_recording", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Recording started: {data.get('message', 'Success')}")
                return True
            else:
                error_data = response.json()
                print(f"❌ Failed to start recording: {error_data.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"❌ Error starting recording: {e}")
            return False
    
    def stop_recording(self):
        """Stop recording and get transcription + analytics"""
        try:
            print("🛑 Stopping recording and processing...")
            response = requests.post(f"{self.stt_server_url}/stop_recording", timeout=60)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Recording stopped and processed!")
                print(f"📝 Transcription: '{data.get('transcription', 'No transcription')}'")
                
                analytics_response = data.get('analytics_response', {})
                if 'response' in analytics_response:
                    print(f"\n📊 Analytics Response:")
                    print(analytics_response['response'])
                elif 'error' in analytics_response:
                    print(f"\n❌ Analytics Error: {analytics_response['error']}")
                
                return data
            else:
                error_data = response.json()
                print(f"❌ Failed to stop recording: {error_data.get('error', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"❌ Error stopping recording: {e}")
            return None
    
    def interactive_mode(self):
        """Run interactive mode for STT control"""
        print("🎤 STT CLIENT - INTERACTIVE MODE")
        print("="*50)
        
        # Check server health first
        if not self.check_health():
            print("❌ Cannot connect to STT server. Make sure it's running.")
            return
        
        print("\n📋 Commands:")
        print("  1 or 'start' - Start recording")
        print("  2 or 'stop'  - Stop recording and process")
        print("  3 or 'status' - Get server status")
        print("  4 or 'health' - Check server health") 
        print("  5 or 'exit'   - Exit")
        print()
        
        while True:
            try:
                command = input("Enter command: ").strip().lower()
                
                if command in ['1', 'start']:
                    self.start_recording()
                    print("📝 Recording... Type 'stop' when done speaking.")
                    
                elif command in ['2', 'stop']:
                    self.stop_recording()
                    
                elif command in ['3', 'status']:
                    self.get_status()
                    
                elif command in ['4', 'health']:
                    self.check_health()
                    
                elif command in ['5', 'exit', 'quit']:
                    print("👋 Goodbye!")
                    break
                    
                else:
                    print("❌ Invalid command. Use 1-5 or start/stop/status/health/exit")
                
                print()  # Add spacing
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except EOFError:
                print("\n👋 Goodbye!")
                break
    
    def quick_record(self, duration=None):
        """Quick recording session"""
        print("🎤 Quick Recording Session")
        print("="*30)
        
        # Check server health
        if not self.check_health():
            return
        
        # Start recording
        if not self.start_recording():
            return
        
        if duration:
            print(f"⏰ Recording for {duration} seconds...")
            time.sleep(duration)
        else:
            print("📝 Recording... Press Enter when done speaking.")
            input()
        
        # Stop recording and get results
        result = self.stop_recording()
        return result

def main():
    parser = argparse.ArgumentParser(description="STT Client for controlling speech-to-text recording")
    
    parser.add_argument("--stt-url", type=str, default="http://localhost:5002",
                       help="URL of STT server")
    parser.add_argument("--mode", type=str, choices=["interactive", "quick"], default="interactive",
                       help="Mode: interactive menu or quick record")
    parser.add_argument("--duration", type=int, default=None,
                       help="Recording duration in seconds (for quick mode)")
    
    args = parser.parse_args()
    
    # Create client
    client = STTClient(args.stt_url)
    
    if args.mode == "interactive":
        client.interactive_mode()
    elif args.mode == "quick":
        client.quick_record(args.duration)

if __name__ == "__main__":
    main()
