import os
import threading
import time
import warnings
import requests
import json
from flask import Flask, request, jsonify
import pyaudio
import numpy as np
import librosa
import whisper

# Set environment variable to avoid library conflicts
os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'

# Suppress common warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="whisper")

class STTServer:
    def __init__(self, model_size="medium", device_index=None, language="en", 
                 csv_analytics_url="http://localhost:5001", port=5002):
        """
        Initialize the STT server that connects to CSV analytics
        """
        self.model_size = model_size
        self.device_index = device_index
        self.language = language
        self.csv_analytics_url = csv_analytics_url
        self.port = port
        
        # Audio recording parameters
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.original_rate = 44100  # High quality recording rate
        self.target_rate = 16000   # Whisper target rate
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Recording control
        self.is_recording = False
        self.recording_thread = None
        self.recorded_frames = []
        self.stream = None
        
        # Flask app
        self.app = Flask(__name__)
        self.setup_routes()
        
        # Initialize Whisper model
        print(f"🤖 Loading Whisper model: {model_size}")
        try:
            self.model = whisper.load_model(model_size)
            print(f"✅ Whisper model loaded successfully!")
        except Exception as e:
            print(f"❌ Error loading Whisper model: {e}")
            raise
        
        print(f"🎤 STT Server initialized on port {port}")
        print(f"🔗 Will connect to CSV Analytics at: {csv_analytics_url}")
    
    def setup_routes(self):
        """Setup Flask routes for STT server"""
        
        @self.app.route('/health', methods=['GET'])
        def health_check():
            """Health check endpoint"""
            return jsonify({"status": "healthy", "recording": self.is_recording})
        
        @self.app.route('/start_recording', methods=['POST'])
        def start_recording_endpoint():
            """Start recording audio"""
            if self.is_recording:
                return jsonify({"error": "Already recording"}), 400
            
            success = self.start_recording()
            if success:
                return jsonify({"message": "Recording started", "status": "recording"})
            else:
                return jsonify({"error": "Failed to start recording"}), 500
        
        @self.app.route('/stop_recording', methods=['POST'])
        def stop_recording_endpoint():
            """Stop recording and process transcription"""
            if not self.is_recording:
                return jsonify({"error": "Not currently recording"}), 400
            
            transcription = self.stop_recording_and_transcribe()
            if transcription:
                # Send transcription to CSV analytics
                analytics_response = self.send_query_to_analytics(transcription)
                return jsonify({
                    "transcription": transcription,
                    "analytics_response": analytics_response,
                    "status": "completed"
                })
            else:
                return jsonify({"error": "No transcription generated"}), 500
        
        @self.app.route('/status', methods=['GET'])
        def get_status():
            """Get current recording status"""
            return jsonify({
                "recording": self.is_recording,
                "model": self.model_size,
                "language": self.language,
                "csv_analytics_url": self.csv_analytics_url
            })
    
    def auto_select_input_device(self):
        """Auto-select the best available input device"""
        devices = []
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'sample_rate': device_info['defaultSampleRate']
                })
        
        if not devices:
            raise Exception("No audio input devices found!")
        
        # Use manually specified device if provided
        if self.device_index is not None:
            device_indices = [d['index'] for d in devices]
            if self.device_index in device_indices:
                return self.device_index
            else:
                print(f"⚠️  Warning: Device index {self.device_index} not found, using auto-selection")
        
        # Try to find the default input device first
        try:
            default_device = self.audio.get_default_input_device_info()
            return default_device['index']
        except:
            # If no default, use the first available device
            return devices[0]['index']
    
    def recording_worker(self):
        """Worker thread for continuous audio recording"""
        input_device = self.auto_select_input_device()
        
        # Get device info and try different sample rates
        device_info = self.audio.get_device_info_by_index(input_device)
        device_rate = int(device_info['defaultSampleRate'])
        
        # Use device's native sample rate or fallback to common rates
        for rate in [device_rate, 44100, 48000, 22050, 16000]:
            try:
                self.stream = self.audio.open(
                    format=self.format,
                    channels=self.channels,
                    rate=rate,
                    input=True,
                    input_device_index=input_device,
                    frames_per_buffer=self.chunk
                )
                self.original_rate = rate
                break
            except Exception as e:
                if rate == 16000:  # Last attempt
                    raise Exception(f"Could not open audio stream: {e}")
                continue
        
        print(f"🎤 Recording started at {self.original_rate}Hz")
        self.recorded_frames = []
        
        try:
            while self.is_recording:
                try:
                    data = self.stream.read(self.chunk, exception_on_overflow=False)
                    self.recorded_frames.append(data)
                    
                    # Show real-time feedback
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    if len(audio_data) > 0:
                        volume = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                        if volume > 500:  # Threshold for detecting speech
                            print("📝 ", end="", flush=True)
                    
                except Exception as e:
                    print(f"Warning: Audio read error: {e}")
                    continue
                    
        except Exception as e:
            print(f"Recording error: {e}")
        finally:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
    
    def start_recording(self):
        """Start recording audio"""
        if self.is_recording:
            print("❌ Already recording!")
            return False
        
        self.is_recording = True
        self.recording_thread = threading.Thread(target=self.recording_worker)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        print("✅ Recording started!")
        return True
    
    def stop_recording_and_transcribe(self):
        """Stop recording and transcribe the audio"""
        if not self.is_recording:
            print("❌ Not currently recording!")
            return None
        
        print("\n🛑 Stopping recording...")
        self.is_recording = False
        
        # Wait for recording thread to finish
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
        
        # Process and transcribe the recorded audio
        if self.recorded_frames:
            try:
                # Convert recorded frames to audio data
                audio_data = np.frombuffer(b''.join(self.recorded_frames), dtype=np.int16)
                audio_data = audio_data.astype(np.float64) / 32768.0
                
                print(f"🔄 Processing audio: {self.original_rate} Hz → {self.target_rate} Hz")
                
                # High-quality resampling if needed
                if self.original_rate != self.target_rate:
                    audio_data = librosa.resample(
                        audio_data, 
                        orig_sr=self.original_rate, 
                        target_sr=self.target_rate,
                        res_type='kaiser_best'
                    )
                
                # Normalize and enhance audio
                if np.max(np.abs(audio_data)) > 0:
                    audio_data = audio_data / np.max(np.abs(audio_data)) * 0.85
                
                # Apply pre-emphasis filter
                pre_emphasis = np.float64(0.95)
                audio_data = np.append(audio_data[0], audio_data[1:] - pre_emphasis * audio_data[:-1])
                
                # Apply noise gate
                noise_threshold = np.float64(0.005)
                audio_data = np.where(np.abs(audio_data) > noise_threshold, audio_data, np.float64(0))
                
                # Ensure correct dtype for Whisper
                audio_data = audio_data.astype(np.float32)
                
                print("🎯 Transcribing with Whisper...")
                
                # Transcribe with Whisper
                result = self.model.transcribe(
                    audio_data, 
                    language=self.language,
                    task="transcribe",
                    temperature=0.0,
                    best_of=5,
                    beam_size=5,
                    patience=1.0,
                    length_penalty=1.0,
                    suppress_tokens=[-1],
                    initial_prompt=None,
                    condition_on_previous_text=True,
                    fp16=False,
                    compression_ratio_threshold=2.4,
                    logprob_threshold=-1.0,
                    no_speech_threshold=0.6,
                )
                
                transcription = result["text"].strip()
                
                if transcription:
                    print(f"📋 Transcription: '{transcription}'")
                    return transcription
                else:
                    print("🔇 No speech detected")
                    return None
                
            except Exception as e:
                print(f"❌ Transcription error: {e}")
                return None
        else:
            print("❌ No audio data recorded")
            return None
    
    def send_query_to_analytics(self, query):
        """Send transcribed query to CSV analytics system"""
        try:
            print(f"🔗 Sending query to CSV Analytics: '{query}'")
            
            # Send POST request to csv_ana.py endpoint
            response = requests.post(
                f"{self.csv_analytics_url}/process_query",
                json={"query": query},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Analytics response received")
                return result
            else:
                print(f"❌ Analytics server error: {response.status_code}")
                return {"error": f"Analytics server returned {response.status_code}"}
                
        except requests.exceptions.ConnectionError:
            print(f"❌ Could not connect to CSV Analytics at {self.csv_analytics_url}")
            return {"error": "Could not connect to CSV Analytics server"}
        except requests.exceptions.Timeout:
            print(f"⏰ Timeout connecting to CSV Analytics")
            return {"error": "Timeout connecting to CSV Analytics"}
        except Exception as e:
            print(f"❌ Error sending query to analytics: {e}")
            return {"error": str(e)}
    
    def cleanup(self):
        """Clean up resources"""
        if self.is_recording:
            self.is_recording = False
            if self.recording_thread:
                self.recording_thread.join(timeout=2.0)
        
        if hasattr(self, 'audio'):
            self.audio.terminate()
    
    def run(self):
        """Run the STT server"""
        print(f"🚀 Starting STT Server on port {self.port}")
        print(f"📡 Endpoints available:")
        print(f"   GET  /health - Health check")
        print(f"   GET  /status - Recording status")
        print(f"   POST /start_recording - Start recording")
        print(f"   POST /stop_recording - Stop recording and process")
        print()
        
        try:
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        except KeyboardInterrupt:
            print("\n🛑 Server stopped by user")
        finally:
            self.cleanup()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="STT Server for CSV Analytics")
    
    # Model parameters
    parser.add_argument("--model-size", type=str, default="medium",
                       choices=["tiny", "base", "small", "medium", "large"],
                       help="Whisper model size")
    parser.add_argument("--language", type=str, default="en",
                       help="Language for transcription")
    parser.add_argument("--device-index", type=int, default=None,
                       help="Audio input device index")
    
    # Server parameters
    parser.add_argument("--port", type=int, default=5002,
                       help="Port for STT server")
    parser.add_argument("--csv-analytics-url", type=str, default="http://localhost:5001",
                       help="URL of CSV Analytics server")
    
    # Device listing
    parser.add_argument("--list-devices", action="store_true",
                       help="List available audio input devices and exit")
    
    args = parser.parse_args()
    
    # If listing devices, show them and exit
    if args.list_devices:
        print("🎧 Available Audio Input Devices:")
        print("="*50)
        import pyaudio
        temp_audio = pyaudio.PyAudio()
        for i in range(temp_audio.get_device_count()):
            device_info = temp_audio.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0:
                is_default = ""
                try:
                    default_device = temp_audio.get_default_input_device_info()
                    if i == default_device['index']:
                        is_default = " [DEFAULT]"
                except:
                    pass
                print(f"  {i}: {device_info['name']}{is_default}")
                print(f"     - Channels: {device_info['maxInputChannels']}")
                print(f"     - Sample Rate: {device_info['defaultSampleRate']:.0f} Hz")
                print()
        temp_audio.terminate()
        return
    
    # Create and run STT server
    stt_server = STTServer(
        model_size=args.model_size,
        device_index=args.device_index,
        language=args.language,
        csv_analytics_url=args.csv_analytics_url,
        port=args.port
    )
    
    stt_server.run()

if __name__ == "__main__":
    main()
