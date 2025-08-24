import openai
from flask import Flask, request, Response, jsonify
import time
from openai import OpenAI
import json
import re
from datetime import datetime, timedelta
 
client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama'
)

# Flask App Setup
app = Flask(__name__)

def get_current_date_context():
    """Get current date context for LLM"""
    now = datetime.now()
    return {
        "current_date": now.strftime("%Y-%m-%d"),
        "current_day": now.strftime("%A"),
        "current_month": now.strftime("%B"),
        "current_year": now.strftime("%Y"),
        "current_week": now.isocalendar()[1],
        "days_in_month": (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
    }

def extract_date_context(user_input):
    """Extract date-related context from user input to help with tool selection"""
    user_lower = user_input.lower()
    
    # Date patterns that indicate time-based analysis
    date_patterns = {
        'weekly': ['week', 'weekly', '7 days', 'seven days'],
        'monthly': ['month', 'monthly', '30 days', 'thirty days', 'quarter', 'q1', 'q2', 'q3', 'q4'],
        'yearly': ['year', 'yearly', 'annual', '365 days'],
        'daily': ['day', 'daily', 'today', 'yesterday'],
        'custom_range': ['from', 'to', 'between', 'range', 'period']
    }
    
    detected_periods = []
    for period, patterns in date_patterns.items():
        if any(pattern in user_lower for pattern in patterns):
            detected_periods.append(period)
    
    return detected_periods

def get_enhanced_tool_descriptions(tools, user_input):
    """Enhance tool descriptions with date context awareness"""
    date_context = extract_date_context(user_input)
    
    enhanced_tools = []
    for tool in tools:
        enhanced_tool = tool.copy()
        
        # Add date context to tool descriptions
        if date_context:
            if 'weekly' in date_context:
                enhanced_tool['description'] += " [OPTIMAL_FOR: Weekly analysis, 7-14 day ranges]"
            if 'monthly' in date_context:
                enhanced_tool['description'] += " [OPTIMAL_FOR: Monthly analysis, 30-90 day ranges]"
            if 'yearly' in date_context:
                enhanced_tool['description'] += " [OPTIMAL_FOR: Yearly analysis, 365+ day ranges]"
            if 'daily' in date_context:
                enhanced_tool['description'] += " [OPTIMAL_FOR: Daily analysis, 1-7 day ranges]"
            if 'custom_range' in date_context:
                enhanced_tool['description'] += " [OPTIMAL_FOR: Custom date ranges, specific periods]"
        
        enhanced_tools.append(enhanced_tool)
    
    return enhanced_tools

# Helper function to handle tool calling with LLM-powered date parsing
def handle_tool_calling(user_input, tools):
    if not tools:
        # No tools provided, just return normal response
        response = client.chat.completions.create(
            model='gpt-oss:20b',
            messages=[{"role": "user", "content": user_input}],
            temperature=0.7,
            stream=False
        )
        return {
            "type": "text_response",
            "content": response.choices[0].message.content
        }
    
    # Get current date context
    date_context = get_current_date_context()
    
    # Create a prompt that instructs the LLM to choose a tool AND parse date ranges
    tool_selection_prompt = f"""
You are a trip analytics assistant with enhanced date range support. The user has asked: "{user_input}"

Current Date Context:
- Today's Date: {date_context['current_date']}
- Current Day: {date_context['current_day']}
- Current Month: {date_context['current_month']}
- Current Year: {date_context['current_year']}
- Current Week: {date_context['current_week']}

Available tools:
{json.dumps(tools, indent=2)}

Your task: Analyze the user's query and return a JSON response with:
1. The most appropriate tool to use
2. Properly formatted date range (start_date and end_date in YYYY-MM-DD format)
3. Period type classification

IMPORTANT: You must respond with ONLY a JSON object in this exact format:
{{
    "type": "tool_call",
    "tool_call": {{
        "name": "tool_name_here",
        "arguments": {{
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD", 
            "period_type": "daily|weekly|monthly|yearly|custom",
            "date_description": "human readable description of the date range"
        }}
    }}
}}

**Date Range Parsing Rules:**
- "last week" → 7 days ending yesterday
- "last 2 weeks" → 14 days ending yesterday  
- "past month" → previous calendar month
- "last 3 months" → 90 days ending yesterday
- "month of June" → June 1-30 of current year (or previous if June has passed)
- "Q1 2024" → January 1, 2024 to March 31, 2024
- "last quarter" → previous quarter based on current date
- "last 45 days" → exactly 45 days ending yesterday
- "this year" → January 1 to current date
- "2024-01-01 to 2024-03-31" → exact date range

**Tool Selection Rules:**
- For queries about "cancelled trips", "cancellations", "failed trips" → use "get_trip_cancellations"
- For queries about "completed trips", "completions", "successful trips" → use "get_trip_completions"  
- For queries about "on-time pickup", "punctuality", "pickup rate", "being on schedule" → use "get_on_time_pickup_analysis"
- For queries about "trip time", "average time", "duration", "how long trips take" → use "get_trip_time_analysis"
- For queries about "completion rate", "percentage", "success rate" → use "get_completion_rate_analysis"
- For queries about "performance comparison", "benchmarking", "daily vs weekly" → use "get_performance_benchmarking"
- For queries about "performance patterns", "heatmap", "intensity mapping" → use "get_performance_heatmap"
- For queries about "metric relationships", "comprehensive analysis", "dashboard", "overview" → use "get_weekly_trip_summary"
- For general queries, "overview", "summary", "analysis", "weekly data" → use "get_weekly_trip_summary"

**Examples:**
- User: "Show me last 2 weeks cancellations"
  Response: {{
    "type": "tool_call",
    "tool_call": {{
      "name": "get_trip_cancellations",
      "arguments": {{
        "start_date": "2024-12-01",
        "end_date": "2024-12-14",
        "period_type": "weekly",
        "date_description": "Last 2 weeks (Dec 1-14, 2024)"
      }}
    }}
  }}

- User: "Analyze month of June performance"
  Response: {{
    "type": "tool_call", 
    "tool_call": {{
      "name": "get_performance_benchmarking",
      "arguments": {{
        "start_date": "2024-06-01",
        "end_date": "2024-06-30", 
        "period_type": "monthly",
        "date_description": "Month of June 2024"
      }}
    }}
  }}

If the user's query doesn't match any specific tool, respond with:
{{
    "type": "text_response",
    "content": "I can help you analyze your trip data! Please specify what aspect you'd like to analyze (completions, cancellations, trip times, performance, etc.) and include a date range like 'last week', 'past month', or 'month of June'."
}}

Remember: ONLY return valid JSON, no other text!
"""

    try:
        response = client.chat.completions.create(
            model='gpt-oss:20b',
            messages=[{"role": "user", "content": tool_selection_prompt}],
            temperature=0.1,  # Lower temperature for more consistent tool selection
            stream=False
        )
        
        llm_response = response.choices[0].message.content.strip()
        print(f"LLM Response: {llm_response}")
        
        # Try to parse the LLM response as JSON
        try:
            parsed_response = json.loads(llm_response)
            
            # Validate the response structure
            if isinstance(parsed_response, dict):
                if parsed_response.get('type') == 'tool_call' and 'tool_call' in parsed_response:
                    tool_call = parsed_response['tool_call']
                    tool_name = tool_call.get('name')
                    arguments = tool_call.get('arguments', {})
                    
                    print(f"✅ LLM chose tool: {tool_name}")
                    print(f"📅 Date range: {arguments.get('start_date')} to {arguments.get('end_date')}")
                    print(f"📊 Period type: {arguments.get('period_type')}")
                    
                    # Validate tool name exists in available tools
                    available_tool_names = [tool['name'] for tool in tools]
                    if tool_name in available_tool_names:
                        return parsed_response
                    else:
                        print(f"⚠️ LLM chose invalid tool: {tool_name}")
                        return {
                            "type": "text_response",
                            "content": f"I understand you want to analyze trip data, but I'm not sure which specific analysis would be best. Available options include: trip summaries, cancellations, completions, trip times, on-time pickup rates, performance benchmarking, and more. Please let me know what specific aspect you'd like to analyze."
                        }
                        
                elif parsed_response.get('type') == 'text_response' and 'content' in parsed_response:
                    print("💬 LLM provided text response")
                    return parsed_response
                else:
                    print("⚠️ Invalid response structure, falling back to text")
                    return {
                        "type": "text_response",
                        "content": "I can help you analyze your trip data! Please specify what you'd like to analyze and include a date range like 'last week' or 'past month'."
                    }
            else:
                print("⚠️ Response not a dict, falling back to text")
                return {
                    "type": "text_response",
                    "content": "I can help you analyze your trip data! Please specify what you'd like to analyze and include a date range like 'last week' or 'past month'."
                }
                
        except json.JSONDecodeError:
            print("⚠️ Could not parse JSON, falling back to text response")
            return {
                "type": "text_response",
                "content": "I can help you analyze your trip data! Please specify what you'd like to analyze and include a date range like 'last week' or 'past month'."
            }
            
    except Exception as e:
        print(f"Error in tool calling: {e}")
        return {
            "type": "text_response",
            "content": f"I encountered an error while processing your request. Please try again with a specific query like 'Show me last week's trip data' or 'Analyze past month performance'."
        }

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get('user_input')
        tools = request.json.get('tools')
        tool_choice = request.json.get('tool_choice', 'auto')
        
        print(f"User Input: {user_input}")
        print(f"Tools: {tools}")
        print(f"Tool Choice: {tool_choice}")
        
        # Handle tool calling if tools are provided
        if tools and tool_choice == 'auto':
            print("🔧 Processing tool calling request with LLM-powered date parsing...")
            result = handle_tool_calling(user_input, tools)
            return jsonify(result)
        else:
            # No tools, just normal chat
            print("💬 Processing normal chat request...")
            response = client.chat.completions.create(
                model='gpt-oss:20b',
                messages=[{"role": "user", "content": user_input}],
                temperature=0.7,
                stream=False
            )
            return jsonify({
                "type": "text_response",
                "content": response.choices[0].message.content
            })
            
    except Exception as e:
        print(f"Error in chat endpoint: {e}")
        return jsonify({'error': str(e)}), 400

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "service": "LLM Server with Date Parsing",
        "version": "3.0",
        "features": [
            "Enhanced tool selection",
            "LLM-powered date range parsing", 
            "Trip analytics support",
            "Dynamic chart adaptation",
            "Natural language date understanding"
        ]
    })

if __name__ == '__main__':
    print("🚀 Starting Enhanced LLM Server with Date Parsing...")
    print("✨ Features:")
    print("   • LLM-powered date range extraction")
    print("   • Natural language date understanding")
    print("   • Automatic date format conversion")
    print("   • Enhanced tool selection")
    print("   • Performance optimization")
    print(f"🌐 Server running on: http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)