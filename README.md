# 🚀 Trip Analytics Voice-Activated System

A **revolutionary voice-activated analytics platform** that transforms natural language queries into **intelligent, dynamic, and professional-grade data visualizations** with beautiful metallic themes and **real-time adaptive capabilities**.

## ✨ **What's New in Version 3.0**

- **🧠 LLM-Powered Date Parsing**: Natural language date understanding
- **📅 Dynamic Date Range Support**: Any time period from days to years
- **🎨 Intelligent Chart Adaptation**: Automatic bar/line chart selection
- **⚡ Real-Time Performance**: Handles any dataset size automatically
- **🎯 Smart Time Grouping**: Daily/Weekly/Monthly/Yearly based on data
- **🚀 Enhanced Voice Commands**: More natural and flexible queries

## 🚀 **Core Features**

- **🎤 Voice-Activated Analytics**: Speak naturally to generate charts
- **🧠 LLM-Powered Intelligence**: Natural language understanding and date parsing
- **📊 Dynamic Chart Generation**: Automatically adapts to any data size or time period
- **🎨 Professional Metallic Themes**: Bronze, Steel, Emerald, Royal color schemes
- **⚡ Real-Time Speech Recognition**: Powered by OpenAI Whisper
- **🎯 Intelligent Tool Selection**: Automatic chart type and time grouping selection
- **🏗️ Multi-Server Architecture**: Scalable and modular design
- **📱 Real-Time Adaptation**: Handles datasets from 1 day to multiple years

## 📋 System Requirements

- Python 3.8+
- macOS, Linux, or Windows
- Microphone for voice input
- 4GB+ RAM recommended
- Internet connection for LLM server

## 🏗️ Architecture

The system consists of four main components:

1. **STT Client** (`stt_client.py`) - Voice input interface
2. **STT Server** (`stt_server.py`) - Audio processing and transcription
3. **Analytics Server** (`csv_ana_server.py`) - Chart generation engine
4. **LLM Server** (`server_side.py`) - Natural language processing

## 📦 **Installation**

1. **Clone or download** the project files
2. **Install dependencies**:
   ```bash
   pip install -r requirements_final.txt
   ```
3. **Prepare your data**: Place CSV file with trip data in the project directory
4. **Set up environment**: Configure your OpenAI API key if using external LLM

## 🔧 Configuration

### **CSV Data Format**
Your CSV file should contain these columns:
- `Date` - Date of the trip (YYYY-MM-DD format)
- `Status` - 'Completed' or 'Cancelled'
- `Trip_Time` - Trip duration in minutes
- `On_Time_Pickup` - 'Yes' or 'No' for punctuality
- `Pickup_Time` - Actual pickup time
- `Dropoff_Time` - Drop-off time

### **Dynamic Date Range Support**
The system now supports **any time period**:
- **"last 2 weeks"** → Automatically calculates date range
- **"month of June"** → Converts to YYYY-MM-DD format
- **"Q1 2024"** → Intelligent quarter calculation
- **"last 45 days"** → Flexible relative date parsing

### **LLM Server Configuration**
Update the LLM server URL in `csv_ana_server.py`:
```python
LLM_SERVER_URL = 'http://your-llm-server:5000/chat'
```

### **Smart Chart Adaptation**
The system automatically selects optimal visualization:
- **≤ 21 days**: Bar charts for clear daily comparison
- **> 21 days**: Line charts for trend analysis
- **Time Grouping**: Daily (≤7 days) → Weekly (≤35 days) → Monthly (≤400 days) → Yearly (>400 days)

## 🚀 Quick Start

### Option 1: Voice-Activated Mode

1. **Start the Analytics Server**:
```bash
   python csv_ana_server.py --csv Generated_Trip_Data.csv --port 5001
   ```

2. **Start the STT Server**:
```bash
   python stt_server.py --port 5002
```

3. **Use the STT Client**:
```bash
   python stt_client.py
   ```

4. **Speak your queries**:
   - "Show me last month's trip summary"
   - "What about trip time analysis for the past 2 weeks?"
   - "Generate performance heatmap for Q1 2024"
   - "Show me last 45 days performance"
   - "Give me the pickup rate analysis for June"

### Option 2: Direct HTTP Queries

Send POST requests to `http://localhost:5001/process_query`:
```bash
curl -X POST http://localhost:5001/process_query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me weekly trip summary"}'
```

## 🎨 **Available Chart Types**

### **Dynamic Analytics Tools**
- **🚀 Weekly Trip Summary**: Comprehensive overview with adaptive time grouping
- **⏱️ Trip Time Analysis**: Duration analysis with intelligent chart type selection
- **⏰ On-Time Pickup Analysis**: Punctuality metrics with dual-axis visualization
- **🏆 Performance Benchmarking**: Period-based performance comparison
- **🔥 Performance Heatmap**: Intensity patterns with adaptive time grouping

### **Smart Features**
- **📅 Automatic Date Range Detection**: Understands natural language time references
- **🎨 Intelligent Chart Selection**: Bar vs Line based on data characteristics
- **⚡ Real-Time Adaptation**: Handles any dataset size automatically
- **🎯 Performance Zones**: Color-coded excellence/good/improvement areas

## 🎨 Chart Themes

Switch between professional dark metallic themes:

```python
# Available themes
csv_ana_server.set_color_theme('dark_bronze')    # Rich copper tones
csv_ana_server.set_color_theme('dark_steel')     # Charcoal elegance
csv_ana_server.set_color_theme('dark_emerald')   # Forest sophistication
csv_ana_server.set_color_theme('dark_royal')     # Midnight majesty
```

## 🌐 API Endpoints

### Analytics Server (Port 5001)
- `POST /process_query` - Process natural language queries
- `GET /charts` - List available chart files
- `GET /chart/<filename>` - Serve chart images

### STT Server (Port 5002)
- `POST /transcribe` - Transcribe audio to text
- `POST /process_voice_query` - Complete voice-to-chart pipeline

## 📊 **Example Queries**

### **🎯 Natural Language Date Queries**
- **"Show me last month's trip summary"**
- **"What about trip time analysis for the past 2 weeks?"**
- **"Generate performance heatmap for Q1 2024"**
- **"Show me last 45 days performance"**
- **"Give me the pickup rate analysis for June"**

### **📅 Flexible Time References**
- **"last week"** → Automatically calculates date range
- **"month of December"** → Converts to YYYY-MM-DD
- **"past quarter"** → Intelligent quarter calculation
- **"last 30 days"** → Flexible relative date parsing
- **"this year"** → Current year analysis

### **🎨 Chart-Specific Queries**
- **"Create a performance heatmap for last month"**
- **"Show performance benchmarking for Q1"**
- **"Generate on-time pickup analysis for the past 2 weeks"**
- **"What's the trip time trend for last quarter?"**

## 🛠️ Troubleshooting

### Common Issues

1. **Audio Input Problems**:
   - Check microphone permissions
   - Verify PyAudio installation
   - Test with `python -m pyaudio`

2. **LLM Server Connection**:
   - Verify server URL and port
   - Check network connectivity
   - Ensure LLM server is running

3. **Chart Display Issues**:
   - Charts auto-open in system viewer
   - Check PNG files in `charts/` directory
   - Verify matplotlib backend compatibility

### Port Conflicts
If ports are in use, modify in the startup commands:
```bash
python csv_ana_server.py --port 5003
python stt_server.py --port 5004
```

## 📁 **File Structure**

```
Open Ai sdk/
├── 🚀 csv_ana_server.py          # Main analytics server (Port 5001)
│   ├── Dynamic date range support
│   ├── Intelligent chart adaptation
│   ├── Beautiful metallic themes
│   └── Real-time data processing
├── 🎤 stt_server.py              # Speech-to-text server (Port 5002)
│   ├── Real-time audio recording
│   ├── Whisper-based transcription
│   └── Voice command processing
├── 🎧 stt_client.py              # Voice input client
│   ├── Audio streaming interface
│   └── Transcription display
├── 🧠 server_side.py             # LLM processing server (Port 5000)
│   ├── Natural language date parsing
│   ├── Intelligent tool selection
│   └── Dynamic query understanding
├── 📊 Generated_Trip_Data.csv    # Sample trip data
├── 📋 requirements_final.txt     # Complete dependencies
├── 📖 README.md                  # This file
└── 🎯 charts/                    # Generated chart files
```

## 🎯 **Performance Tips**

- **💾 Use SSD storage** for faster chart generation
- **🧠 Allocate 4GB+ RAM** for optimal performance
- **🔒 Close unnecessary applications** during heavy processing
- **🌐 Use wired network** for stable LLM communication
- **⚡ Enable real-time processing** for dynamic chart adaptation

## 🚀 **Dynamic System Capabilities**

### **📅 Intelligent Date Parsing**
- **Natural Language**: "last month", "past 2 weeks", "Q1 2024"
- **Flexible Formats**: "month of June", "last quarter", "this year"
- **Relative References**: "last 45 days", "past 3 months"
- **Specific Periods**: "2024-01-01 to 2024-03-31"

### **🎨 Smart Chart Adaptation**
- **Data Size**: Automatically chooses bar vs line charts
- **Time Grouping**: Daily → Weekly → Monthly → Yearly
- **Performance Zones**: Color-coded excellence indicators
- **Real-Time Updates**: Adapts to any dataset changes

### **🧠 LLM-Powered Intelligence**
- **Query Understanding**: Natural language processing
- **Tool Selection**: Automatic analytics tool choice
- **Date Conversion**: YYYY-MM-DD format generation
- **Context Awareness**: Understands business terminology

## 🔒 Security Notes

- **Local Processing**: Audio and data processed locally
- **Network Security**: Use HTTPS for production LLM servers
- **Data Privacy**: No data sent to external services except configured LLM
- **Port Security**: Consider firewall rules for production deployment

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📋 **Requirements & Dependencies**

### **Complete Requirements File**
- **`requirements_final.txt`**: Contains ALL dependencies for the complete system
- **Comprehensive Coverage**: Web frameworks, data processing, AI, audio processing
- **Version Specifications**: Minimum version requirements for stability
- **Installation Notes**: Platform-specific setup instructions

### **Key Dependencies**
- **Flask**: Web server framework for all components
- **Pandas + NumPy**: Data processing and analysis
- **Matplotlib**: Professional chart generation
- **OpenAI**: LLM integration and natural language processing
- **PyAudio + Whisper**: Speech recognition and audio processing

### **Installation Command**
```bash
pip install -r requirements_final.txt
```

## 📄 License

This project is for educational and research purposes. Please review and comply with all third-party library licenses.

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the system workflow diagram
3. Test individual components separately
4. Check server logs for detailed error messages

## 🎉 Acknowledgments

- **OpenAI Whisper** for speech recognition
- **Matplotlib** for chart generation
- **Flask** for web server framework
- **Pandas** for data processing
- **NumPy** for numerical computations