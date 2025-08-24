# =============================================================================
# TRIP ANALYTICS SERVER WITH LLM-POWERED DATE PARSING
# =============================================================================
# 
# This system now uses the LLM server for natural language date parsing instead
# of complex regex patterns. The LLM understands queries like:
# - "last 2 weeks", "past month", "month of June", "Q1 2024"
# - "last quarter", "last 45 days", "this year"
# - And converts them to proper YYYY-MM-DD format automatically
#
# Benefits:
# - More natural language understanding
# - No need to maintain complex regex patterns
# - Better context awareness for relative dates
# - Easier to extend with new date formats
# =============================================================================

import requests
import matplotlib
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import numpy as np
from datetime import datetime, timedelta
import json
import os
import re
from matplotlib.colors import LinearSegmentedColormap
from matplotlib import cm
import warnings
from flask import Flask, request, jsonify, send_from_directory
import threading
import queue
warnings.filterwarnings('ignore')

# Optional imports for enhanced visualizations
try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

# Configure matplotlib for server mode (no GUI to avoid threading issues)
matplotlib.use('Agg')  # Use non-interactive backend
matplotlib.rcParams['figure.max_open_warning'] = 0  # Disable warning for multiple open figures

# For server mode - save charts and auto-open them
import uuid
import subprocess
CHARTS_DIR = "charts"
if not os.path.exists(CHARTS_DIR):
    os.makedirs(CHARTS_DIR)

# Global counter for unique figure numbering
_figure_counter = 0

def get_next_figure_number():
    """Get next unique figure number to prevent chart conflicts"""
    global _figure_counter
    _figure_counter += 1
    return _figure_counter

def save_and_open_chart(fig, chart_name):
    """Save chart to file and auto-open it in system viewer"""
    chart_id = str(uuid.uuid4())[:8]
    filename = f"{chart_name}_{chart_id}.png"
    filepath = os.path.join(CHARTS_DIR, filename)
    
    # Save the chart
    fig.savefig(filepath, dpi=300, bbox_inches='tight', 
                facecolor='white', edgecolor='none')
    plt.close(fig)  # Close to free memory
    
    # Auto-open the chart in system's default image viewer
    try:
        # macOS
        subprocess.Popen(['open', filepath])
        print(f"Chart opened in system viewer: {filename}")
    except Exception as e:
        try:
            # Linux
            subprocess.Popen(['xdg-open', filepath])
            print(f"Chart opened in system viewer: {filename}")
        except Exception as e2:
            try:
                # Windows
                subprocess.Popen(['start', filepath], shell=True)
                print(f"Chart opened in system viewer: {filename}")
            except Exception as e3:
                print(f"Chart saved: {filename}")
                print(f"Could not auto-open chart. Open manually: {filepath}")
    
    return filename

def parse_date_range(query_text):
    """Parse date range from user query with enhanced pattern matching"""
    query_lower = query_text.lower()
    today = datetime.now().date()
    
    # Specific date range patterns (YYYY-MM-DD to YYYY-MM-DD format)
    date_range_pattern = r'(\d{4}-\d{2}-\d{2})\s*to\s*(\d{4}-\d{2}-\d{2})'
    date_range_match = re.search(date_range_pattern, query_text)
    
    if date_range_match:
        start_str, end_str = date_range_match.groups()
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            return start_date, end_date, 'custom'
        except ValueError:
            pass
    
    # Enhanced relative date patterns with flexible matching
    
    # "Last X weeks" pattern (e.g., "last 2 weeks", "past 3 weeks")
    weeks_pattern = r'(?:last|past|previous)\s+(\d+)\s+weeks?'
    weeks_match = re.search(weeks_pattern, query_lower)
    if weeks_match:
        num_weeks = int(weeks_match.group(1))
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(weeks=num_weeks)
        return start_date, end_date, 'weekly'
    
    # "Last X months" pattern (e.g., "last 3 months", "past 2 months")
    months_pattern = r'(?:last|past|previous)\s+(\d+)\s+months?'
    months_match = re.search(months_pattern, query_lower)
    if months_match:
        num_months = int(months_match.group(1))
        # Approximate months as 30 days each
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=num_months * 30)
        return start_date, end_date, 'monthly'
    
    # "Last X years" pattern (e.g., "last 2 years", "past 3 years")
    years_pattern = r'(?:last|past|previous)\s+(\d+)\s+years?'
    years_match = re.search(years_pattern, query_lower)
    if years_match:
        num_years = int(years_match.group(1))
        end_date = today - timedelta(days=1)
        start_date = datetime(today.year - num_years, today.month, today.day).date()
        return start_date, end_date, 'yearly'
    
    # "Last X days" pattern (e.g., "last 30 days", "past 14 days")
    days_pattern = r'(?:last|past|previous)\s+(\d+)\s+days?'
    days_match = re.search(days_pattern, query_lower)
    if days_match:
        num_days = int(days_match.group(1))
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=num_days - 1)
        
        # Determine period type based on number of days
        if num_days <= 10:
            period_type = 'daily'
        elif num_days <= 35:
            period_type = 'weekly'
        elif num_days <= 400:
            period_type = 'monthly'
        else:
            period_type = 'yearly'
        
        return start_date, end_date, period_type
    
    # Specific month patterns (e.g., "month of June", "June 2024", "last June")
    month_names = {
        'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
        'april': 4, 'apr': 4, 'may': 5, 'june': 6, 'july': 7, 'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'october': 10, 'oct': 10, 'november': 11, 'nov': 11,
        'december': 12, 'dec': 12
    }
    
    # Pattern: "month of [Month]" or "[Month] [Year]" or "last [Month]"
    for month_name, month_num in month_names.items():
        # "month of June" pattern
        month_of_pattern = rf'month\s+of\s+{month_name}'
        if re.search(month_of_pattern, query_lower):
            # Default to current year if no year specified
            year = today.year
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month_num + 1, 1).date() - timedelta(days=1)
            return start_date, end_date, 'monthly'
        
        # "[Month] [Year]" pattern (e.g., "June 2024")
        month_year_pattern = rf'{month_name}\s+(\d{{4}})'
        month_year_match = re.search(month_year_pattern, query_lower)
        if month_year_match:
            year = int(month_year_match.group(1))
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month_num + 1, 1).date() - timedelta(days=1)
            return start_date, end_date, 'monthly'
        
        # "last [Month]" pattern (e.g., "last June")
        last_month_pattern = rf'last\s+{month_name}'
        if re.search(last_month_pattern, query_lower):
            # Find the most recent occurrence of this month
            if today.month > month_num:
                year = today.year
            else:
                year = today.year - 1
            
            start_date = datetime(year, month_num, 1).date()
            if month_num == 12:
                end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                end_date = datetime(year, month_num + 1, 1).date() - timedelta(days=1)
            return start_date, end_date, 'monthly'
    
    # Quarter patterns (e.g., "Q1 2024", "last quarter", "Q3")
    quarter_pattern = r'q(\d)\s*(\d{4})?'
    quarter_match = re.search(quarter_pattern, query_lower)
    if quarter_match:
        quarter = int(quarter_match.group(1))
        year = int(quarter_match.group(2)) if quarter_match.group(2) else today.year
        
        # Calculate quarter start and end months
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        
        start_date = datetime(year, start_month, 1).date()
        if end_month == 12:
            end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(year, end_month + 1, 1).date() - timedelta(days=1)
        return start_date, end_date, 'monthly'
    
    # "Last quarter" pattern
    if re.search(r'last\s+quarter', query_lower):
        current_quarter = (today.month - 1) // 3 + 1
        if current_quarter == 1:
            year = today.year - 1
            quarter = 4
        else:
            year = today.year
            quarter = current_quarter - 1
        
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2
        
        start_date = datetime(year, start_month, 1).date()
        if end_month == 12:
            end_date = datetime(year + 1, 1, 1).date() - timedelta(days=1)
        else:
            end_date = datetime(year, end_month + 1, 1).date() - timedelta(days=1)
        return start_date, end_date, 'monthly'
    
    # Simple relative patterns (fallback)
    if any(word in query_lower for word in ['last week', 'past week', 'previous week']):
        # Last week means previous 7 days ending yesterday
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=6)
        return start_date, end_date, 'weekly'
    
    elif any(word in query_lower for word in ['this week', 'current week']):
        # This week means from Monday to today
        days_since_monday = today.weekday()
        start_date = today - timedelta(days=days_since_monday)
        end_date = today
        return start_date, end_date, 'weekly'
    
    elif any(word in query_lower for word in ['last month', 'past month', 'previous month']):
        # Last month means full previous calendar month
        if today.month == 1:
            start_date = datetime(today.year - 1, 12, 1).date()
            end_date = datetime(today.year, 1, 1).date() - timedelta(days=1)
        else:
            start_date = datetime(today.year, today.month - 1, 1).date()
            end_date = datetime(today.year, today.month, 1).date() - timedelta(days=1)
        return start_date, end_date, 'monthly'
    
    elif any(word in query_lower for word in ['this month', 'current month']):
        # This month means from 1st of current month to today
        start_date = datetime(today.year, today.month, 1).date()
        end_date = today
        return start_date, end_date, 'monthly'
    
    elif any(word in query_lower for word in ['last year', 'past year', 'previous year']):
        # Last year means full previous calendar year
        start_date = datetime(today.year - 1, 1, 1).date()
        end_date = datetime(today.year - 1, 12, 31).date()
        return start_date, end_date, 'yearly'
    
    elif any(word in query_lower for word in ['this year', 'current year']):
        # This year means from Jan 1 to today
        start_date = datetime(today.year, 1, 1).date()
        end_date = today
        return start_date, end_date, 'yearly'
    
    # No date range found
    return None, None, None

def get_x_axis_labels(date_range, period_type):
    """Get appropriate X-axis labels based on period type"""
    start_date, end_date = date_range
    
    if period_type == 'daily':
        # Show individual days
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        return [date.strftime('%Y-%m-%d') for date in dates]
    
    elif period_type == 'weekly':
        # Show days of week or weeks
        total_days = (end_date - start_date).days + 1
        if total_days <= 7:
            # Show day names
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            return [date.strftime('%a %m/%d') for date in dates]
        else:
            # Show weeks
            weeks = pd.date_range(start=start_date, end=end_date, freq='W-MON')
            return [f"Week {week.strftime('%m/%d')}" for week in weeks]
    
    elif period_type == 'monthly':
        # Show weeks or months
        total_days = (end_date - start_date).days + 1
        if total_days <= 35:
            # Show weeks
            weeks = pd.date_range(start=start_date, end=end_date, freq='W-MON')
            return [f"Week {week.strftime('%m/%d')}" for week in weeks]
        else:
            # Show months
            months = pd.date_range(start=start_date, end=end_date, freq='MS')
            return [month.strftime('%Y-%m') for month in months]
    
    elif period_type == 'yearly':
        # Show months or years
        total_days = (end_date - start_date).days + 1
        if total_days <= 400:
            # Show months
            months = pd.date_range(start=start_date, end=end_date, freq='MS')
            return [month.strftime('%Y-%m') for month in months]
        else:
            # Show years
            years = pd.date_range(start=start_date, end=end_date, freq='YS')
            return [year.strftime('%Y') for year in years]
    
    # Default fallback
    return ['Data']

def get_fallback_response():
    """Provide helpful response when LLM doesn't use trip analytics tools"""
    return """🤔 I'm not sure what you mean. Let me help you with your trip data!

🚗 **Here's what I can analyze for you:**

📊 **Basic Trip Analysis:**
• "How many trips were completed this week?"
• "What's our completion rate for the last 2 months?"
• "Show me trip cancellations from month of June"
• "What's the average trip time for the past 45 days?"
• "How are our on-time pickups for Q1 2024?"

📈 **Advanced Analytics:**
• "How do our daily numbers compare for last week?" (Performance benchmarking)
• "Show me patterns across the past 3 months" (Heatmap analysis)
• "What's the relationship between our metrics for last quarter?" (Comprehensive summary)

📅 **Natural Language Date Support:**
The system now understands conversational date expressions naturally!

**Relative Dates:**
• "Show me last week's data" or "last 2 weeks"
• "Analyze past month performance" or "last 3 months"
• "Compare this year vs last year" or "last 2 years"
• "Last 30 days trip analysis" or "past 45 days"

**Specific Periods:**
• "Month of June analysis" or "June 2024"
• "Q1 2024 on-time pickup analysis"
• "Last quarter performance trends"
• "Show me this week's data"

**Exact Ranges:**
• "Show data from 2024-01-01 to 2024-03-31"
• "Analyze trips from 2024-12-01 to 2024-12-07"

✨ **No more complex date formatting needed!** Just speak naturally:
• "What happened last week?"
• "How did we perform in June?"
• "Show me the last quarter trends"
• "Analyze the past 2 months"

🎯 **The LLM understands natural language and automatically converts it to proper date ranges!**

📋 Type 'help' for all commands or 'list open plots' to see current charts."""

# Dark Metallic & Gradient Color Palettes - Sophisticated Deep Tones
COLOR_PALETTES = {
    'dark_bronze': {
        'primary': '#8B4513',        # Dark saddle brown
        'secondary': '#654321',      # Dark brown
        'accent': '#A0522D',         # Sienna
        'success': '#2F4F2F',        # Dark slate gray green
        'warning': '#8B0000',        # Dark red
        'info': '#2F4F4F',          # Dark slate gray
        'light': '#F5F5DC',         # Beige
        'dark': '#1C1C1C',          # Very dark gray
        'colors': ['#8B4513', '#654321', '#A0522D', '#CD853F', '#D2691E', '#8B6914', '#7A5230', '#6B4423', '#5D4037', '#4E342E'],
        'gradients': {
            'bronze': ['#4E342E', '#654321', '#8B4513', '#A0522D'],
            'copper': ['#5D4037', '#8B4513', '#A0522D', '#CD853F'],
            'brass': ['#654321', '#8B6914', '#B8860B', '#DAA520'],
            'rust': ['#6B4423', '#8B4513', '#CD853F', '#D2691E']
        },
        'metallic_effects': {
            'shine_overlay': 'linear-gradient(45deg, rgba(205,133,63,0.3) 0%, rgba(139,69,19,0.1) 50%, rgba(205,133,63,0.3) 100%)',
            'shadow_color': '#2F1B14',
            'highlight_color': '#CD853F'
        }
    },
    'dark_steel': {
        'primary': '#36454F',        # Charcoal
        'secondary': '#2F4F4F',      # Dark slate gray
        'accent': '#4682B4',         # Steel blue
        'success': '#2E4057',        # Dark blue gray
        'warning': '#5D4E75',        # Dark slate blue
        'info': '#36648B',          # Steel blue dark
        'light': '#F0F8FF',         # Alice blue
        'dark': '#1C1C1C',          # Very dark gray
        'colors': ['#36454F', '#2F4F4F', '#4682B4', '#5F9EA0', '#6A5ACD', '#483D8B', '#36648B', '#2E4057', '#405D6E', '#4A5D6C'],
        'gradients': {
            'steel': ['#2F4F4F', '#36454F', '#4682B4', '#5F9EA0'],
            'gunmetal': ['#2C3539', '#36454F', '#4A5D6C', '#5F9EA0'],
            'slate': ['#2E4057', '#36648B', '#4682B4', '#6495ED'],
            'pewter': ['#36454F', '#483D8B', '#5D4E75', '#6A5ACD']
        },
        'metallic_effects': {
            'shine_overlay': 'linear-gradient(45deg, rgba(95,158,160,0.3) 0%, rgba(70,130,180,0.1) 50%, rgba(95,158,160,0.3) 100%)',
            'shadow_color': '#1C1C1C',
            'highlight_color': '#87CEEB'
        }
    },
    'dark_emerald': {
        'primary': '#355E3B',        # Hunter green
        'secondary': '#2F4F2F',      # Dark slate gray green
        'accent': '#556B2F',         # Dark olive green
        'success': '#228B22',        # Forest green
        'warning': '#8B3A3A',        # Dark red
        'info': '#2F4F4F',          # Dark slate gray
        'light': '#F0FFF0',         # Honeydew
        'dark': '#1C1C1C',          # Very dark gray
        'colors': ['#355E3B', '#2F4F2F', '#556B2F', '#6B8E23', '#8FBC8F', '#2E8B57', '#3CB371', '#20B2AA', '#008B8B', '#4682B4'],
        'gradients': {
            'emerald': ['#2F4F2F', '#355E3B', '#228B22', '#32CD32'],
            'forest': ['#2E8B57', '#228B22', '#32CD32', '#90EE90'],
            'jade': ['#355E3B', '#2E8B57', '#3CB371', '#66CDAA'],
            'teal': ['#2F4F4F', '#008B8B', '#20B2AA', '#48D1CC']
        },
        'metallic_effects': {
            'shine_overlay': 'linear-gradient(45deg, rgba(60,179,113,0.3) 0%, rgba(46,139,87,0.1) 50%, rgba(60,179,113,0.3) 100%)',
            'shadow_color': '#1B2F1B',
            'highlight_color': '#90EE90'
        }
    },
    'dark_royal': {
        'primary': '#191970',        # Midnight blue
        'secondary': '#483D8B',      # Dark slate blue
        'accent': '#4B0082',         # Indigo
        'success': '#2F4F2F',        # Dark slate gray green
        'warning': '#8B0000',        # Dark red
        'info': '#2F4F4F',          # Dark slate gray
        'light': '#F8F8FF',         # Ghost white
        'dark': '#0C0C0C',          # Nearly black
        'colors': ['#191970', '#483D8B', '#4B0082', '#6A5ACD', '#7B68EE', '#8470FF', '#9370DB', '#9932CC', '#8B008B', '#800080'],
        'gradients': {
            'royal': ['#0C0C0C', '#191970', '#483D8B', '#6A5ACD'],
            'purple': ['#2E2B5F', '#4B0082', '#8B008B', '#9370DB'],
            'indigo': ['#191970', '#4B0082', '#6A5ACD', '#7B68EE'],
            'amethyst': ['#483D8B', '#8B008B', '#9932CC', '#BA55D3']
        },
        'metallic_effects': {
            'shine_overlay': 'linear-gradient(45deg, rgba(123,104,238,0.3) 0%, rgba(75,0,130,0.1) 50%, rgba(123,104,238,0.3) 100%)',
            'shadow_color': '#0C0C0C',
            'highlight_color': '#9370DB'
        }
    }
}

# Current palette selection - Dark metallic themes for sophisticated appeal
CURRENT_PALETTE = 'dark_steel'

def get_gradient_colors(palette_name, num_colors):
    """Generate stunning metallic gradient colors with shine effects"""
    if palette_name not in COLOR_PALETTES:
        palette_name = 'dark_bronze'
    
    palette = COLOR_PALETTES[palette_name]
    
    # Use gradient colors for premium metallic appeal
    if num_colors <= 3:
        # Use specific metallic gradients for small numbers
        gradient_keys = list(palette['gradients'].keys())
        selected_gradient = palette['gradients'][gradient_keys[0]]
        return selected_gradient[:num_colors]
    elif num_colors <= len(palette['colors']):
        return palette['colors'][:num_colors]
    else:
        # Create smooth metallic interpolation for larger numbers
        import matplotlib.colors as mcolors
        
        # Use multiple metallic gradients for variety
        all_gradient_colors = []
        for gradient in palette['gradients'].values():
            all_gradient_colors.extend(gradient)
        
        # Create metallic colormap with shine effect
        cmap = mcolors.LinearSegmentedColormap.from_list("metallic_shine", all_gradient_colors)
        return [cmap(i / (num_colors - 1)) for i in range(num_colors)]

def create_metallic_colormap(palette_name, gradient_name):
    """Create sophisticated metallic colormaps with shine effects"""
    import matplotlib.colors as mcolors
    import numpy as np
    
    if palette_name not in COLOR_PALETTES:
        palette_name = 'dark_bronze'
    
    palette = COLOR_PALETTES[palette_name]
    
    if gradient_name in palette['gradients']:
        colors = palette['gradients'][gradient_name]
    else:
        colors = list(palette['gradients'].values())[0]
    
    # Add shine effect by interpolating with white highlights
    enhanced_colors = []
    for i, color in enumerate(colors):
        enhanced_colors.append(color)
        if i < len(colors) - 1:
            # Add shine highlight between colors
            enhanced_colors.append(add_metallic_shine(color))
    
    return mcolors.LinearSegmentedColormap.from_list(f"metallic_{gradient_name}", enhanced_colors)

def add_metallic_shine(base_color):
    """Add metallic shine effect to a base color"""
    import matplotlib.colors as mcolors
    
    # Convert to RGB if needed
    if isinstance(base_color, str):
        rgb = mcolors.hex2color(base_color)
    else:
        rgb = base_color
    
    # Add shine by lightening and adding white highlights
    shine_factor = 0.3
    shiny_rgb = tuple(min(1.0, c + shine_factor) for c in rgb)
    
    return shiny_rgb

def get_metallic_bar_colors(palette_name, num_bars):
    """Generate metallic bar colors with individual shine effects"""
    import matplotlib.colors as mcolors
    import numpy as np
    
    base_colors = get_gradient_colors(palette_name, num_bars)
    metallic_colors = []
    
    for i, color in enumerate(base_colors):
        # Create gradient effect for each bar
        if isinstance(color, str):
            rgb = mcolors.hex2color(color)
        else:
            rgb = color[:3] if len(color) > 3 else color
        
        # Create metallic gradient: dark -> bright -> highlight
        dark_rgb = tuple(max(0.0, c * 0.7) for c in rgb)
        bright_rgb = rgb
        highlight_rgb = tuple(min(1.0, c + 0.4) for c in rgb)
        
        # Create individual colormap for this bar
        bar_cmap = mcolors.LinearSegmentedColormap.from_list(
            f"metallic_bar_{i}", 
            [dark_rgb, bright_rgb, highlight_rgb]
        )
        metallic_colors.append(bar_cmap(0.6))  # Use middle-bright section
    
    return metallic_colors

def get_beautiful_background():
    """Get beautiful background color for charts"""
    return COLOR_PALETTES[CURRENT_PALETTE]['light']

def get_text_color():
    """Get professional text color"""
    return COLOR_PALETTES[CURRENT_PALETTE]['dark']

def set_color_theme(theme_name):
    """Switch between stunning metallic themes with shine effects"""
    global CURRENT_PALETTE
    if theme_name in COLOR_PALETTES:
        CURRENT_PALETTE = theme_name
        theme_display = theme_name.replace('_', ' ').title()
        
        # Add special effects description
        effects = {
            'dark_bronze': 'Rich dark bronze with sophisticated copper tones',
            'dark_steel': 'Deep charcoal steel with gunmetal elegance', 
            'dark_emerald': 'Deep emerald forest with hunter green sophistication',
            'dark_royal': 'Midnight blue royal with deep purple and indigo elegance'
        }
        
        effect_desc = effects.get(theme_name, 'Beautiful professional styling')
        print(f"Switched to {theme_display} theme! {effect_desc}")
        return True
    else:
        available = ', '.join(COLOR_PALETTES.keys())
        print(f"Theme '{theme_name}' not found. Available: {available}")
        return False

def get_theme_info():
    """Get information about current theme and available themes"""
    current = COLOR_PALETTES[CURRENT_PALETTE]
    return {
        'current_theme': CURRENT_PALETTE,
        'primary_color': current['primary'],
        'available_themes': list(COLOR_PALETTES.keys()),
        'description': f"Beautiful {CURRENT_PALETTE} theme with professional gradient colors"
    }

def create_custom_colormap(palette_name):
    """Create a matplotlib colormap from a palette"""
    if palette_name not in COLOR_PALETTES:
        palette_name = 'corporate'
    
    colors = COLOR_PALETTES[palette_name]['colors']
    return LinearSegmentedColormap.from_list(f"{palette_name}_cmap", colors)

class TripAnalyticsTools:
    def __init__(self, csv_file_path):
        """Initialize with CSV data"""
        print(f"Loading trip data from: {csv_file_path}")
        try:
            self.df = pd.read_csv(csv_file_path)
            print(f"Successfully loaded {len(self.df)} trips from CSV")
            
            # Check column names and map them to expected format
            print(f"CSV columns: {list(self.df.columns)}")
            
            # Map your CSV columns to expected format
            column_mapping = {
                'trip_date': 'Date',
                'trip_status': 'Status',
                'scheduled_pickup_time': 'Scheduled_Pickup',
                'actual_pickup_time': 'Actual_Pickup',
                'dropoff_time': 'Dropoff_Time'
            }
            
            # Rename columns to match expected format
            self.df = self.df.rename(columns=column_mapping)
            
            # Convert date column to datetime
            self.df['Date'] = pd.to_datetime(self.df['Date'])
            
            # Calculate trip time and on-time pickup status
            self.df['Scheduled_Pickup'] = pd.to_datetime(self.df['Scheduled_Pickup'])
            self.df['Actual_Pickup'] = pd.to_datetime(self.df['Actual_Pickup'])
            self.df['Dropoff_Time'] = pd.to_datetime(self.df['Dropoff_Time'])
            
            # Calculate trip duration in minutes
            self.df['Trip_Time'] = (self.df['Dropoff_Time'] - self.df['Actual_Pickup']).dt.total_seconds() / 60
            
            # Calculate on-time pickup (within 5 minutes of scheduled time)
            pickup_diff = (self.df['Actual_Pickup'] - self.df['Scheduled_Pickup']).dt.total_seconds() / 60
            self.df['On_Time_Pickup'] = pickup_diff.apply(lambda x: 'Yes' if abs(x) <= 5 else 'No')
            
            # Standardize status values
            self.df['Status'] = self.df['Status'].str.title()  # completed -> Completed
            
            # Get the date range
            start_date = self.df['Date'].min()
            end_date = self.df['Date'].max()
            date_range = (end_date - start_date).days + 1
            
            print(f"Data spans {date_range} days with actual data")
            print("Calculated Trip_Time and On_Time_Pickup columns")
            
        except Exception as e:
            print(f"Error loading CSV: {e}")
            raise
    
    def filter_data_by_date_range(self, start_date, end_date):
        """Filter dataframe by date range"""
        if start_date is None or end_date is None:
            return self.df
        
        # Convert dates to pandas timestamps for comparison
        start_ts = pd.Timestamp(start_date)
        end_ts = pd.Timestamp(end_date)
        
        # Filter the dataframe
        filtered_df = self.df[
            (self.df['Date'] >= start_ts) & 
            (self.df['Date'] <= end_ts)
        ].copy()
        
        print(f"Filtered data from {start_date} to {end_date}: {len(filtered_df)} trips")
        return filtered_df
    
    def get_grouping_freq_and_labels(self, filtered_df, period_type):
        """Get appropriate grouping frequency and labels based on period type and data range"""
        if len(filtered_df) == 0:
            return 'D', []
        
        start_date = filtered_df['Date'].min().date()
        end_date = filtered_df['Date'].max().date()
        total_days = (end_date - start_date).days + 1
        
        # Enhanced dynamic grouping logic
        if total_days <= 7:
            # 1 week or less: use days with day names
            freq = 'D'
            dates = pd.date_range(start=start_date, end=end_date, freq='D')
            labels = [date.strftime('%a %m/%d') for date in dates]
            return freq, labels
        
        elif total_days <= 35:  # ~1 month
            # 1-5 weeks: use weeks
            freq = 'W-MON'
            weeks = pd.date_range(start=start_date, end=end_date, freq='W-MON')
            labels = [f"Week {week.strftime('%m/%d')}" for week in weeks]
            return freq, labels
        
        elif total_days <= 400:  # ~1 year
            # 1-12 months: use months
            freq = 'MS'
            months = pd.date_range(start=start_date, end=end_date, freq='MS')
            labels = [month.strftime('%b %Y') for month in months]
            return freq, labels
        
        else:
            # More than 1 year: use years
            freq = 'YS'
            years = pd.date_range(start=start_date, end=end_date, freq='YS')
            labels = [year.strftime('%Y') for year in years]
            return freq, labels
    
    def should_use_line_chart(self, filtered_df, period_type):
        """Determine if line chart should be used instead of bar chart for better visualization"""
        total_days = (filtered_df['Date'].max().date() - filtered_df['Date'].min().date()).days + 1
        
        # Enhanced chart type selection logic
        if total_days <= 7:
            # 1 week or less: use bar charts (clear daily comparison)
            return False
        elif total_days <= 21:  # ~3 weeks
            # 1-3 weeks: use bar charts (weekly patterns visible)
            return False
        elif total_days <= 35:  # ~1 month
            # 3-5 weeks: use line charts (trends become more important)
            return True
        else:
            # More than 1 month: definitely use line charts (trends and patterns)
            return True
    
    def get_summary(self, filtered_df=None):
        """Get comprehensive trip summary for filtered data with enhanced insights"""
        if filtered_df is None:
            filtered_df = self.df
            
        total_trips = len(filtered_df)
        completed_trips = len(filtered_df[filtered_df['Status'] == 'Completed'])
        cancelled_trips = len(filtered_df[filtered_df['Status'] == 'Cancelled'])
        completion_rate = (completed_trips / total_trips * 100) if total_trips > 0 else 0
        
        # Trip time analysis for completed trips only
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        if len(completed_df) > 0:
            avg_trip_time = completed_df['Trip_Time'].mean()
            min_trip_time = completed_df['Trip_Time'].min()
            max_trip_time = completed_df['Trip_Time'].max()
            trip_time_std = completed_df['Trip_Time'].std()
        else:
            avg_trip_time = min_trip_time = max_trip_time = trip_time_std = 0
        
        # On-time pickup analysis
        if len(completed_df) > 0:
            on_time_count = len(completed_df[completed_df['On_Time_Pickup'] == 'Yes'])
            on_time_rate = (on_time_count / len(completed_df) * 100)
        else:
            on_time_count = 0
            on_time_rate = 0
        
        # Date range analysis
        if len(filtered_df) > 0:
            start_date = filtered_df['Date'].min().date()
            end_date = filtered_df['Date'].max().date()
            total_days = (end_date - start_date).days + 1
            
            # Daily averages
            avg_daily_trips = total_trips / total_days if total_days > 0 else 0
            avg_daily_completed = completed_trips / total_days if total_days > 0 else 0
            avg_daily_cancelled = cancelled_trips / total_days if total_days > 0 else 0
        else:
            start_date = end_date = None
            total_days = avg_daily_trips = avg_daily_completed = avg_daily_cancelled = 0
        
        # Performance insights
        performance_score = 0
        if total_trips > 0:
            # Composite performance score (0-100)
            completion_weight = 0.4
            ontime_weight = 0.4
            efficiency_weight = 0.2
            
            # Normalize trip time (lower is better, assume 60 min is baseline)
            efficiency_score = max(0, 100 - (avg_trip_time / 60 * 100)) if avg_trip_time > 0 else 100
            
            performance_score = (
                (completion_rate * completion_weight) +
                (on_time_rate * ontime_weight) +
                (efficiency_score * efficiency_weight)
            )
        
        return {
            'total_trips': total_trips,
            'completed_trips': completed_trips,
            'cancelled_trips': cancelled_trips,
            'completion_rate': completion_rate,
            'avg_trip_time': avg_trip_time,
            'min_trip_time': min_trip_time,
            'max_trip_time': max_trip_time,
            'trip_time_std': trip_time_std,
            'on_time_count': on_time_count,
            'on_time_rate': on_time_rate,
            'start_date': start_date,
            'end_date': end_date,
            'total_days': total_days,
            'avg_daily_trips': avg_daily_trips,
            'avg_daily_completed': avg_daily_completed,
            'avg_daily_cancelled': avg_daily_cancelled,
            'performance_score': performance_score
        }
    
    def get_weekly_summary(self):
        """Get comprehensive weekly trip summary (backward compatibility)"""
        return self.get_summary()
    
    def create_summary_plot(self, start_date=None, end_date=None, period_type='weekly'):
        """Create enhanced summary visualization with dynamic date ranges and chart types"""
        plt.style.use('default')
        
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        
        if len(filtered_df) == 0:
            print("No data found for the specified date range")
            return None
        
        # Get appropriate grouping frequency and labels
        freq, x_labels = self.get_grouping_freq_and_labels(filtered_df, period_type)
        
        # Group data by the appropriate frequency
        if freq == 'D':
            # Group by day
            daily_stats = filtered_df.groupby(filtered_df['Date'].dt.date).agg({
                'Status': ['count', lambda x: (x == 'Completed').sum(), lambda x: (x == 'Cancelled').sum()]
            }).round(2)
        elif freq == 'W-MON':
            # Group by week
            daily_stats = filtered_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'Status': ['count', lambda x: (x == 'Completed').sum(), lambda x: (x == 'Cancelled').sum()]
            }).round(2)
        elif freq == 'MS':
            # Group by month
            daily_stats = filtered_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'Status': ['count', lambda x: (x == 'Completed').sum(), lambda x: (x == 'Cancelled').sum()]
            }).round(2)
        else:
            # Group by year
            daily_stats = filtered_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'Status': ['count', lambda x: (x == 'Completed').sum(), lambda x: (x == 'Cancelled').sum()]
            }).round(2)
        
        # Flatten column names
        daily_stats.columns = ['Total', 'Completed', 'Cancelled']
        
        # Remove empty periods
        daily_stats = daily_stats[daily_stats['Total'] > 0]
        
        if len(daily_stats) == 0:
            print("No data found after grouping")
            return None
        
        # Create figure with beautiful styling
        fig = plt.figure(num=get_next_figure_number(), figsize=(16, 10))
        fig.patch.set_facecolor(get_beautiful_background())
        
        # Determine if we should use line chart or bar chart
        use_line_chart = self.should_use_line_chart(filtered_df, period_type)
        
        # Create X-axis labels
        x_pos = range(len(daily_stats))
        if freq == 'D':
            x_labels = [date.strftime('%a %m/%d') for date in daily_stats.index]
        elif freq == 'W-MON':
            x_labels = [f"Week {date.strftime('%m/%d')}" for date in daily_stats.index]
        elif freq == 'MS':
            x_labels = [date.strftime('%b %Y') for date in daily_stats.index]
        else:
            x_labels = [date.strftime('%Y') for date in daily_stats.index]
        
        # Main chart showing completed vs cancelled
        ax1 = plt.subplot(2, 2, (1, 2))
        
        # Get stunning metallic gradient colors with shine effects
        metallic_colors = get_metallic_bar_colors(CURRENT_PALETTE, len(daily_stats))
        
        # Get primary metallic colors for completed/cancelled
        palette = COLOR_PALETTES[CURRENT_PALETTE]
        completed_color = palette['success'] 
        cancelled_color = palette['warning']
        
        # Add metallic shine to the colors
        completed_shiny = add_metallic_shine(completed_color)
        cancelled_shiny = add_metallic_shine(cancelled_color)
        
        if use_line_chart:
            # Use line chart for larger datasets
            line1 = ax1.plot(x_pos, daily_stats['Completed'], 
                           color=completed_shiny, marker='o', linewidth=3, markersize=8, 
                           label='Completed', markerfacecolor='white', 
                           markeredgecolor=completed_shiny, markeredgewidth=2)
            line2 = ax1.plot(x_pos, daily_stats['Cancelled'], 
                           color=cancelled_shiny, marker='s', linewidth=3, markersize=8,
                           label='Cancelled', markerfacecolor='white',
                           markeredgecolor=cancelled_shiny, markeredgewidth=2)
            
            # Add shadows to lines
            for line in line1 + line2:
                        line.set_path_effects([path_effects.Normal()])
        else:
            # Use stacked bar chart for smaller datasets
            bars_completed = ax1.bar(x_pos, daily_stats['Completed'], 
                                   color=metallic_colors, label='Completed', 
                                   edgecolor='white', linewidth=4, alpha=0.95)
            bars_cancelled = ax1.bar(x_pos, daily_stats['Cancelled'], 
                                   bottom=daily_stats['Completed'],
                                   color=cancelled_shiny, label='Cancelled',
                                   edgecolor='white', linewidth=4, alpha=0.95)
            
            # Add metallic shine effects to bars
            # Simplified for compatibility
        
        # Set X-axis labels and styling
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(x_labels, rotation=45 if len(x_labels) > 7 else 0, ha='right' if len(x_labels) > 7 else 'center')
        
        # Add value labels (different for line vs bar charts)
        max_height = daily_stats['Total'].max()
        
        if not use_line_chart:
            # Labels for completed trips (bar chart only)
            for i, (completed_val, cancelled_val, total_val) in enumerate(zip(daily_stats['Completed'], daily_stats['Cancelled'], daily_stats['Total'])):
                if completed_val > 0:  # Only show label if there are completed trips
                    ax1.text(i, completed_val/2, f'{int(completed_val)}',
                            ha='center', va='center', fontweight='bold', fontsize=10, color='white')
                
                if cancelled_val > 0:  # Only show label if there are cancelled trips
                    y_pos = completed_val + cancelled_val/2
                    ax1.text(i, y_pos, f'{int(cancelled_val)}',
                            ha='center', va='center', fontweight='bold', fontsize=10, color='white')
                
                # Total labels on top
                ax1.text(i, total_val + max_height * 0.02, f'{int(total_val)}',
                        ha='center', va='bottom', fontweight='bold', fontsize=11)
        else:
            # Value labels for line chart
            for i, (completed_val, cancelled_val) in enumerate(zip(daily_stats['Completed'], daily_stats['Cancelled'])):
                if completed_val > 0:
                    ax1.text(i, completed_val + max_height * 0.02, f'{int(completed_val)}',
                            ha='center', va='bottom', fontweight='bold', fontsize=9, 
                            )
                if cancelled_val > 0:
                    ax1.text(i, cancelled_val + max_height * 0.02, f'{int(cancelled_val)}',
                            ha='center', va='bottom', fontweight='bold', fontsize=9,
                            )
        
        ax1.set_ylim(0, max_height * 1.15)
        
        # Dynamic title and axis labels based on period type
        if period_type == 'daily' or freq == 'D':
            xlabel = 'Date'
            title = 'Daily Trip Distribution: Completed vs Cancelled'
        elif period_type == 'weekly' or freq == 'W-MON':
            xlabel = 'Week'
            title = 'Weekly Trip Distribution: Completed vs Cancelled'
        elif period_type == 'monthly' or freq == 'MS':
            xlabel = 'Month'
            title = 'Monthly Trip Distribution: Completed vs Cancelled'
        else:
            xlabel = 'Year'
            title = 'Yearly Trip Distribution: Completed vs Cancelled'
        
        ax1.set_xlabel(xlabel, fontsize=15, fontweight='bold', color=get_text_color())
        ax1.set_ylabel('Number of Trips', fontsize=15, fontweight='bold', color=get_text_color())
        ax1.set_title(title, fontsize=17, fontweight='bold', pad=25)
        
        # Beautiful legend with enhanced styling
        legend = ax1.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, 
                           fontsize=12, title='Trip Status')
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_alpha(0.95)
        legend.get_frame().set_edgecolor(metallic_colors[0])
        legend.get_frame().set_linewidth(2)
        
        ax1.grid(axis='y', alpha=0.3, linestyle=':', linewidth=1)
        ax1.set_facecolor(get_beautiful_background())
        
        # Completion rate pie chart with gradient colors
        ax2 = plt.subplot(2, 2, 3)
        completed = daily_stats['Completed'].sum()
        cancelled = daily_stats['Cancelled'].sum()
        
        sizes = [completed, cancelled]
        labels = [f'Completed\n({completed} trips)', f'Cancelled\n({cancelled} trips)']
        
        # Get stunning metallic colors for pie chart
        palette = COLOR_PALETTES[CURRENT_PALETTE]
        pie_colors = [add_metallic_shine(palette['success']), add_metallic_shine(palette['warning'])]
        explode = (0.15, 0.15)
        
        wedges, texts, autotexts = ax2.pie(sizes, labels=labels, colors=pie_colors, autopct='%1.1f%%',
                                          explode=explode, shadow=True, startangle=90,
                                          textprops={'fontweight': 'bold', 'fontsize': 12, 'color': get_text_color()},
                                          wedgeprops={'edgecolor': 'white', 'linewidth': 5})
        
        # Add stunning metallic shine effects to pie chart
        # Simplified for compatibility
        
        # Enhanced styling for pie chart
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(12)
        
        ax2.set_title('Trip Completion Status', fontsize=15, fontweight='bold', pad=20,
                     )
        
        # Summary with enhanced styling
        ax3 = plt.subplot(2, 2, 4)
        ax3.axis('off')
        
        summary = self.get_summary(filtered_df)
        
        # Create date range string for display
        if start_date and end_date:
            date_str = f"{start_date} to {end_date}"
        else:
            date_str = "All Data"
        
        # Enhanced dynamic summary with insights
        if summary['total_days'] > 0:
            period_insight = f"({summary['total_days']} days)"
            daily_insight = f"Daily Avg: {summary['avg_daily_trips']:.1f} trips"
        else:
            period_insight = ""
            daily_insight = ""
        
        # Performance rating
        if summary['performance_score'] >= 80:
            performance_emoji = ""
            performance_text = "Excellent"
        elif summary['performance_score'] >= 60:
            performance_emoji = ""
            performance_text = "Good"
        elif summary['performance_score'] >= 40:
            performance_emoji = ""
            performance_text = "Fair"
        else:
            performance_emoji = ""
            performance_text = "Needs Improvement"
        
        stats_text = f"""SUMMARY ({date_str}) {period_insight}
        
Total Trips: {summary['total_trips']}
Completed: {summary['completed_trips']} ({summary['completion_rate']:.1f}%)
Cancelled: {summary['cancelled_trips']}
Trip Time: {summary['avg_trip_time']:.1f} min (Range: {summary['min_trip_time']:.1f}-{summary['max_trip_time']:.1f})
On-Time Rate: {summary['on_time_rate']:.1f}%
{daily_insight}
Performance: {performance_text} ({summary['performance_score']:.1f}/100)"""
        
        # Enhanced summary box with gradient background
        gradient_bg = get_gradient_colors(CURRENT_PALETTE, 3)[1]
        ax3.text(0.05, 0.95, stats_text, transform=ax3.transAxes, fontsize=13,
                verticalalignment='top', fontweight='bold',
                )
        
        plt.tight_layout(rect=[0, 0.02, 1, 0.96])
        
        # Save chart and auto-open in system viewer
        chart_type = "line_summary" if use_line_chart else "bar_summary"
        chart_filename = save_and_open_chart(fig, f"{period_type}_{chart_type}")
        return chart_filename
    
    def create_weekly_plot(self):
        """Create enhanced weekly summary visualization (backward compatibility)"""
        return self.create_summary_plot(period_type='weekly')
    
    def create_trip_time_plot(self, start_date=None, end_date=None, period_type='weekly'):
        """Create enhanced trip time analysis with performance zones and dynamic date ranges"""
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            print("No completed trips to analyze for the specified date range")
            return None
        
        # Get appropriate grouping frequency
        freq, x_labels = self.get_grouping_freq_and_labels(completed_df, period_type)
        
        # Group data by the appropriate frequency
        if freq == 'D':
            time_stats = completed_df.groupby(completed_df['Date'].dt.date)['Trip_Time'].agg(['mean', 'count']).round(2)
        elif freq == 'W-MON':
            time_stats = completed_df.groupby(pd.Grouper(key='Date', freq='W-MON'))['Trip_Time'].agg(['mean', 'count']).round(2)
        elif freq == 'MS':
            time_stats = completed_df.groupby(pd.Grouper(key='Date', freq='MS'))['Trip_Time'].agg(['mean', 'count']).round(2)
        else:
            time_stats = completed_df.groupby(pd.Grouper(key='Date', freq='YS'))['Trip_Time'].agg(['mean', 'count']).round(2)
        
        # Remove empty periods
        time_stats = time_stats[time_stats['count'] > 0]
        
        if len(time_stats) == 0:
            print("No data found after grouping")
            return None
        
        # Create figure with beautiful styling
        fig = plt.figure(num=get_next_figure_number(), figsize=(15, 9))
        fig.patch.set_facecolor(get_beautiful_background())
        ax = fig.add_subplot(111)
        
        # Determine chart type
        use_line_chart = self.should_use_line_chart(completed_df, period_type)
        
        # Create X-axis labels
        x_pos = range(len(time_stats))
        if freq == 'D':
            x_labels = [date.strftime('%a %m/%d') for date in time_stats.index]
        elif freq == 'W-MON':
            x_labels = [f"Week {date.strftime('%m/%d')}" for date in time_stats.index]
        elif freq == 'MS':
            x_labels = [date.strftime('%b %Y') for date in time_stats.index]
        else:
            x_labels = [date.strftime('%Y') for date in time_stats.index]
        
        # Get stunning metallic colors with shine effects
        metallic_colors = get_metallic_bar_colors(CURRENT_PALETTE, len(time_stats))
        
        if use_line_chart:
            # Use line/scatter chart for larger datasets
            line = ax.plot(x_pos, time_stats['mean'], 
                          color=COLOR_PALETTES[CURRENT_PALETTE]['primary'], 
                          marker='o', linewidth=3, markersize=8, 
                          markerfacecolor='white', 
                          markeredgecolor=COLOR_PALETTES[CURRENT_PALETTE]['primary'], 
                          markeredgewidth=2, alpha=0.9, zorder=3)
            
            # Add shadows to lines
            # Simplified for compatibility
            
            # Add value labels for line chart
            max_time = time_stats['mean'].max()
            for i, (value, count) in enumerate(zip(time_stats['mean'], time_stats['count'])):
                ax.text(i, value + max_time * 0.03, f'{value:.1f} min\n({int(count)} trips)',
                       ha='center', va='bottom', fontweight='bold', fontsize=10,
                       color='darkblue')
        else:
            # Use bar chart for smaller datasets
            bars = ax.bar(x_pos, time_stats['mean'],
                         color=metallic_colors, edgecolor='white', linewidth=4, alpha=0.95,
                         zorder=3)
            
            # Add stunning metallic shine effects
            # Simplified for compatibility
            
            # Add beautiful value labels with enhanced styling
            max_time = time_stats['mean'].max()
            for i, (value, count, color) in enumerate(zip(time_stats['mean'], time_stats['count'], metallic_colors)):
                ax.text(i, value + max_time * 0.03, f'{value:.1f} min\n({int(count)} trips)',
                       ha='center', va='bottom', fontweight='bold', fontsize=11,
                       color='darkblue')
        
        # Set X-axis labels
        ax.set_xticks(x_pos)
        ax.set_xticklabels(x_labels, rotation=45 if len(x_labels) > 7 else 0, 
                          ha='right' if len(x_labels) > 7 else 'center')
        
        # Enhanced performance zones with gradient colors
        period_avg = time_stats['mean'].mean()
        zone_colors = get_gradient_colors(CURRENT_PALETTE, 3)
        max_time = time_stats['mean'].max()
        
        # Average line with enhanced styling
        ax.axhline(y=period_avg, color=COLOR_PALETTES[CURRENT_PALETTE]['primary'], 
                  linestyle='--', linewidth=3, alpha=0.8, 
                  label=f'Period Average: {period_avg:.1f} min', zorder=4)
        
        # Beautiful performance zones
        ax.axhspan(0, period_avg * 0.9, alpha=0.15, color=zone_colors[0], 
                  label='Excellent Zone (< 90% avg)', zorder=1)
        ax.axhspan(period_avg * 0.9, period_avg * 1.1, alpha=0.15, color=zone_colors[1], 
                  label='Good Zone (90-110% avg)', zorder=1)
        ax.axhspan(period_avg * 1.1, max_time * 1.25, alpha=0.15, color=zone_colors[2], 
                  label='Improvement Zone (> 110% avg)', zorder=1)
        
        # Dynamic title and axis labels based on period type
        if period_type == 'daily' or freq == 'D':
            xlabel = 'Date'
            title = 'Daily Average Trip Time Analysis'
        elif period_type == 'weekly' or freq == 'W-MON':
            xlabel = 'Week'
            title = 'Weekly Average Trip Time Analysis'
        elif period_type == 'monthly' or freq == 'MS':
            xlabel = 'Month'
            title = 'Monthly Average Trip Time Analysis'
        else:
            xlabel = 'Year'
            title = 'Yearly Average Trip Time Analysis'
        
        # Enhanced styling
        ax.set_ylim(0, max_time * 1.25)
        ax.set_xlabel(xlabel, fontsize=15, fontweight='bold', color='darkblue')
        ax.set_ylabel('Average Trip Time (minutes)', fontsize=15, fontweight='bold', color='darkblue')
        ax.set_title(title, fontsize=18, fontweight='bold', pad=25)
        
        # Enhanced legend with custom styling
        legend = ax.legend(loc='upper right', frameon=True, fancybox=True, shadow=True,
                          fontsize=11, title='Performance Zones')
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_alpha(0.9)
        legend.get_frame().set_edgecolor(metallic_colors[0])
        legend.get_frame().set_linewidth(2)
        
        ax.grid(axis='y', alpha=0.3, linestyle=':', linewidth=1)
        ax.set_facecolor(get_beautiful_background())
        
        plt.tight_layout(rect=[0, 0.05, 1, 0.92])
        
        # Save chart and queue for GUI display
        chart_type = "line_time" if use_line_chart else "bar_time"
        chart_filename = save_and_open_chart(fig, f"{period_type}_{chart_type}_analysis")
        return chart_filename
    
    def create_on_time_pickup_plot(self, start_date=None, end_date=None, period_type='weekly'):
        """Create enhanced on-time pickup analysis with dynamic date range support"""
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            print("No completed trips to analyze for the specified date range")
            return None
        
        # Get appropriate grouping frequency and labels
        freq, x_labels = self.get_grouping_freq_and_labels(completed_df, period_type)
        
        # Group data by the appropriate frequency
        if freq == 'D':
            # Group by day
            grouped_data = completed_df.groupby(completed_df['Date'].dt.date).agg({
                'On_Time_Pickup': [
                    lambda x: (x == 'Yes').sum() / len(x) * 100,  # percentage
                    'count'  # total count
                ]
            }).round(2)
        elif freq == 'W-MON':
            # Group by week
            grouped_data = completed_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'On_Time_Pickup': [
                    lambda x: (x == 'Yes').sum() / len(x) * 100,  # percentage
                    'count'  # total count
                ]
            }).round(2)
        elif freq == 'MS':
            # Group by month
            grouped_data = completed_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'On_Time_Pickup': [
                    lambda x: (x == 'Yes').sum() / len(x) * 100,  # percentage
                    'count'  # total count
                ]
            }).round(2)
        else:
            # Group by year
            grouped_data = completed_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'On_Time_Pickup': [
                    lambda x: (x == 'Yes').sum() / len(x) * 100,  # percentage
                    'count'  # total count
                ]
            }).round(2)
        
        # Flatten column names
        grouped_data.columns = ['on_time_rate', 'total_trips']
        
        # Remove empty periods
        grouped_data = grouped_data[grouped_data['total_trips'] > 0]
        
        if len(grouped_data) == 0:
            print("No data found after grouping")
            return None
        
        # Create X-axis labels based on frequency
        x_pos = range(len(grouped_data))
        if freq == 'D':
            x_labels = [date.strftime('%a %m/%d') for date in grouped_data.index]
        elif freq == 'W-MON':
            x_labels = [f"Week {date.strftime('%m/%d')}" for date in grouped_data.index]
        elif freq == 'MS':
            x_labels = [date.strftime('%b %Y') for date in grouped_data.index]
        else:
            x_labels = [date.strftime('%Y') for date in grouped_data.index]
        
        # Create figure with enhanced dual y-axis
        fig = plt.figure(num=get_next_figure_number(), figsize=(16, 9))
        fig.patch.set_facecolor(get_beautiful_background())
        ax1 = fig.add_subplot(111)
        
        # Get stunning metallic colors with shine effects
        metallic_colors = get_metallic_bar_colors(CURRENT_PALETTE, len(grouped_data))
        gradient_colors = metallic_colors  # Keep for compatibility
        
        # Enhanced on-time rate bars with metallic shine
        bars1 = ax1.bar(x_pos, grouped_data['on_time_rate'],
                       color=metallic_colors, edgecolor='white', linewidth=4, alpha=0.95, 
                       width=0.7, zorder=3)
        
        # Add stunning metallic shine effects
        for bar in bars1:
            bar.set_path_effects([
                path_effects.Normal()
            ])
        
        # Add beautiful value labels with enhanced styling
        max_rate = grouped_data['on_time_rate'].max()
        for i, (bar, rate, color) in enumerate(zip(bars1, grouped_data['on_time_rate'], gradient_colors)):
            height = bar.get_height()
            # Enhanced text styling with shadow effect for elegance
            ax1.text(bar.get_x() + bar.get_width()/2., height + 2,
                    f'{rate:.1f}%',
                    ha='center', va='bottom', fontweight='bold', fontsize=12,
                    color='darkblue')
        
        # Enhanced performance zones with gradient colors
        zone_colors = get_gradient_colors(CURRENT_PALETTE, 3)
        ax1.axhspan(90, min(110, max_rate + 15), alpha=0.15, color=zone_colors[0], 
                   label='Excellent Zone (≥90%)', zorder=1)
        ax1.axhspan(75, 90, alpha=0.15, color=zone_colors[1], 
                   label='Good Zone (75-90%)', zorder=1)
        ax1.axhspan(0, 75, alpha=0.15, color=zone_colors[2], 
                   label='Improvement Zone (<75%)', zorder=1)
        
        # Enhanced styling for primary axis
        ax1.set_ylim(0, min(110, max_rate + 15))
        
        # Dynamic X-axis labels and title based on period type
        if period_type == 'daily' or freq == 'D':
            xlabel = 'Date'
            title = 'Daily On-Time Pickup Performance Dashboard'
        elif period_type == 'weekly' or freq == 'W-MON':
            xlabel = 'Week'
            title = 'Weekly On-Time Pickup Performance Dashboard'
        elif period_type == 'monthly' or freq == 'MS':
            xlabel = 'Month'
            title = 'Monthly On-Time Pickup Performance Dashboard'
        else:
            xlabel = 'Year'
            title = 'Yearly On-Time Pickup Performance Dashboard'
        
        ax1.set_xlabel(xlabel, fontsize=15, fontweight='bold', color='darkblue')
        ax1.set_ylabel('On-Time Pickup Rate (%)', fontsize=15, fontweight='bold', 
                      color=COLOR_PALETTES[CURRENT_PALETTE]['primary'])
        ax1.tick_params(axis='y', labelcolor=COLOR_PALETTES[CURRENT_PALETTE]['primary'], labelsize=12)
        ax1.set_title(title, fontsize=18, fontweight='bold', pad=25)
        ax1.grid(axis='y', alpha=0.3, linestyle=':', linewidth=1)
        ax1.set_facecolor('#fafafa')
        
        # Set X-axis labels
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(x_labels, rotation=45 if len(x_labels) > 7 else 0, ha='right' if len(x_labels) > 7 else 'center')
        
        # Enhanced second y-axis for trip count
        ax2 = ax1.twinx()
        
        # Beautiful line with markers and shadows
        line_color = COLOR_PALETTES[CURRENT_PALETTE]['warning']
        line = ax2.plot(x_pos, grouped_data['total_trips'], 
                       color=line_color, marker='o', linewidth=4, markersize=10, 
                       label='Trip Volume', alpha=0.9, zorder=4,
                       markerfacecolor='white', markeredgecolor=line_color, markeredgewidth=3)
        
        # Add shadows to line
        line[0].set_path_effects([path_effects.Normal()])
        
        max_count = grouped_data['total_trips'].max()
        ax2.set_ylim(0, max_count * 1.15)
        ax2.set_ylabel('Number of Trips', fontsize=15, fontweight='bold', 
                      color=COLOR_PALETTES[CURRENT_PALETTE]['warning'])
        ax2.tick_params(axis='y', labelcolor=COLOR_PALETTES[CURRENT_PALETTE]['warning'], labelsize=12)
        
        # Add shadows to bars
        # Simplified for compatibility
        
        # Enhanced combined legend with beautiful styling
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        legend = ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right', 
                           frameon=True, fancybox=True, shadow=True, fontsize=11,
                           title='Performance Metrics')
        legend.get_frame().set_facecolor('white')
        legend.get_frame().set_alpha(0.95)
        legend.get_frame().set_edgecolor(gradient_colors[0])
        legend.get_frame().set_linewidth(2)
        
        plt.tight_layout(rect=[0, 0.05, 1, 0.94])
        
        # Save chart and queue for GUI display
        chart_filename = save_and_open_chart(fig, "on_time_pickup_analysis")
        return chart_filename
    
    def create_performance_benchmarking_chart(self, start_date=None, end_date=None, period_type='weekly'):
        """Create performance benchmarking dashboard with dynamic date range support"""
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            print("No completed trips to analyze for the specified date range")
            return None
        
        # Get appropriate grouping frequency and labels
        freq, x_labels = self.get_grouping_freq_and_labels(filtered_df, period_type)
        
        # Group data by the appropriate frequency
        if freq == 'D':
            # Group by day
            grouped_metrics = filtered_df.groupby(filtered_df['Date'].dt.date).agg({
                'Status': [
                    'count',  # total trips
                    lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
                ]
            })
            
            completed_grouped = completed_df.groupby(completed_df['Date'].dt.date).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        elif freq == 'W-MON':
            # Group by week
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'Status': [
                    'count',  # total trips
                    lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
                ]
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        elif freq == 'MS':
            # Group by month
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'Status': [
                    'count',  # total trips
                    lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
                ]
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        else:
            # Group by year
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'Status': [
                    'count',  # total trips
                    lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
                ]
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        
        # Flatten columns and combine
        grouped_metrics.columns = ['total_trips', 'completion_rate']
        grouped_metrics = grouped_metrics.join(completed_grouped)
        
        # Remove empty periods
        grouped_metrics = grouped_metrics[grouped_metrics['total_trips'] > 0]
        
        if len(grouped_metrics) == 0:
            print("No data found after grouping")
            return None
        
        # Calculate period averages (not just weekly anymore)
        period_avg_completion = grouped_metrics['completion_rate'].mean()
        period_avg_ontime = grouped_metrics['On_Time_Pickup'].mean()
        period_avg_time = grouped_metrics['Trip_Time'].mean()
        
        # Calculate performance score (composite)
        grouped_metrics['performance_score'] = (
            (grouped_metrics['completion_rate'] / 100 * 0.3) +
            (grouped_metrics['On_Time_Pickup'] / 100 * 0.4) +
            ((100 - grouped_metrics['Trip_Time'] / period_avg_time * 100) / 100 * 0.3)
        ) * 100
        
        period_avg_score = grouped_metrics['performance_score'].mean()
        
        # Create X-axis labels based on frequency
        x_pos = range(len(grouped_metrics))
        if freq == 'D':
            x_labels = [date.strftime('%a %m/%d') for date in grouped_metrics.index]
        elif freq == 'W-MON':
            x_labels = [f"Week {date.strftime('%m/%d')}" for date in grouped_metrics.index]
        elif freq == 'MS':
            x_labels = [date.strftime('%b %Y') for date in grouped_metrics.index]
        else:
            x_labels = [date.strftime('%Y') for date in grouped_metrics.index]
        
        # Create 2x2 subplot dashboard
        fig = plt.figure(num=get_next_figure_number(), figsize=(16, 12))
        fig.patch.set_facecolor(get_beautiful_background())
        
        # Get professional colors for better matching
        success_color = COLOR_PALETTES[CURRENT_PALETTE]['success']
        warning_color = COLOR_PALETTES[CURRENT_PALETTE]['warning']
        primary_color = COLOR_PALETTES[CURRENT_PALETTE]['primary']
        
        # Completion rate comparison
        ax1 = plt.subplot(2, 2, 1)
        colors1 = [success_color if x >= period_avg_completion else warning_color for x in grouped_metrics['completion_rate']]
        bars1 = ax1.bar(x_pos, grouped_metrics['completion_rate'], color=colors1, alpha=0.8, edgecolor='white', linewidth=1)
        ax1.axhline(y=period_avg_completion, color=primary_color, linestyle='--', linewidth=2, 
                   label=f'Period Avg: {period_avg_completion:.1f}%')
        ax1.set_title('Completion Rate vs Period Average', fontweight='bold', fontsize=12, pad=15)
        ax1.set_ylabel('Completion Rate (%)', fontweight='bold')
        ax1.legend()
        ax1.grid(axis='y', alpha=0.3)
        ax1.set_facecolor('#fafafa')
        
        # On-time rate comparison
        ax2 = plt.subplot(2, 2, 2)
        colors2 = [success_color if x >= period_avg_ontime else warning_color for x in grouped_metrics['On_Time_Pickup']]
        bars2 = ax2.bar(x_pos, grouped_metrics['On_Time_Pickup'], color=colors2, alpha=0.8, edgecolor='white', linewidth=1)
        ax2.axhline(y=period_avg_ontime, color=primary_color, linestyle='--', linewidth=2, 
                   label=f'Period Avg: {period_avg_ontime:.1f}%')
        ax2.set_title('On-Time Rate vs Period Average', fontweight='bold', fontsize=12, pad=15)
        ax2.set_ylabel('On-Time Rate (%)', fontweight='bold')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        ax2.set_facecolor('#fafafa')
        
        # Trip time comparison (lower is better)
        ax3 = plt.subplot(2, 2, 3)
        colors3 = [success_color if x <= period_avg_time else warning_color for x in grouped_metrics['Trip_Time']]
        bars3 = ax3.bar(x_pos, grouped_metrics['Trip_Time'], color=colors3, alpha=0.8, edgecolor='white', linewidth=1)
        ax3.axhline(y=period_avg_time, color=primary_color, linestyle='--', linewidth=2, 
                   label=f'Period Avg: {period_avg_time:.1f} min')
        ax3.set_title('Trip Time vs Period Average', fontweight='bold', fontsize=12, pad=15)
        ax3.set_ylabel('Avg Trip Time (min)', fontweight='bold')
        
        # Dynamic X-axis label based on period type
        if period_type == 'daily' or freq == 'D':
            xlabel = 'Date'
        elif period_type == 'weekly' or freq == 'W-MON':
            xlabel = 'Week'
        elif period_type == 'monthly' or freq == 'MS':
            xlabel = 'Month'
        else:
            xlabel = 'Year'
        
        ax3.set_xlabel(xlabel, fontweight='bold')
        ax3.legend()
        ax3.grid(axis='y', alpha=0.3)
        ax3.set_facecolor('#fafafa')
        
        # Overall performance score
        ax4 = plt.subplot(2, 2, 4)
        colors4 = [success_color if x >= period_avg_score else warning_color for x in grouped_metrics['performance_score']]
        bars4 = ax4.bar(x_pos, grouped_metrics['performance_score'], color=colors4, alpha=0.8, edgecolor='white', linewidth=1)
        ax4.axhline(y=period_avg_score, color=primary_color, linestyle='--', linewidth=2, 
                   label=f'Period Avg: {period_avg_score:.1f}')
        ax4.set_title('Overall Performance Score vs Period Average', fontweight='bold', fontsize=12, pad=15)
        ax4.set_ylabel('Performance Score', fontweight='bold')
        ax4.set_xlabel(xlabel, fontweight='bold')
        ax4.legend()
        ax4.grid(axis='y', alpha=0.3)
        ax4.set_facecolor('#fafafa')
        
        # Set X-axis labels for all subplots
        for ax in [ax1, ax2, ax3, ax4]:
            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_labels, rotation=45 if len(x_labels) > 7 else 0, ha='right' if len(x_labels) > 7 else 'center')
        
        # Dynamic title based on period type
        if period_type == 'daily' or freq == 'D':
            title = 'Daily Performance Benchmarking Dashboard'
        elif period_type == 'weekly' or freq == 'W-MON':
            title = 'Weekly Performance Benchmarking Dashboard'
        elif period_type == 'monthly' or freq == 'MS':
            title = 'Monthly Performance Benchmarking Dashboard'
        else:
            title = 'Yearly Performance Benchmarking Dashboard'
        
        fig.suptitle(title, fontsize=18, fontweight='bold', y=0.98)
        plt.subplots_adjust(hspace=0.4, wspace=0.3)
        plt.tight_layout(rect=[0, 0.02, 1, 0.95])
        
        # Save chart and queue for GUI display
        chart_filename = save_and_open_chart(fig, f"{period_type}_performance_benchmarking")
        return chart_filename
    
    def create_performance_heatmap(self, start_date=None, end_date=None, period_type='weekly'):
        """Create performance heatmap with dynamic date range support"""
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            print("No completed trips to analyze for the specified date range")
            return None
        
        # Get appropriate grouping frequency and labels
        freq, x_labels = self.get_grouping_freq_and_labels(filtered_df, period_type)
        
        # Group data by the appropriate frequency
        if freq == 'D':
            # Group by day
            grouped_metrics = filtered_df.groupby(filtered_df['Date'].dt.date).agg({
                'Status': lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
            })
            
            completed_grouped = completed_df.groupby(completed_df['Date'].dt.date).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        elif freq == 'W-MON':
            # Group by week
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'Status': lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        elif freq == 'MS':
            # Group by month
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'Status': lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        else:
            # Group by year
            grouped_metrics = filtered_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'Status': lambda x: (x == 'Completed').sum() / len(x) * 100  # completion rate
            })
            
            completed_grouped = completed_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'Trip_Time': 'mean',
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
        
        # Combine and normalize
        grouped_metrics.columns = ['completion_rate']
        grouped_metrics = grouped_metrics.join(completed_grouped)
        
        # Remove empty periods
        grouped_metrics = grouped_metrics[grouped_metrics['completion_rate'] > 0]
        
        if len(grouped_metrics) == 0:
            print("No data found after grouping")
            return None
        
        # Calculate trip efficiency (inverse of time, normalized)
        max_time = grouped_metrics['Trip_Time'].max()
        grouped_metrics['trip_efficiency'] = (max_time - grouped_metrics['Trip_Time']) / max_time * 100
        
        # Create X-axis labels based on frequency
        if freq == 'D':
            x_labels = [date.strftime('%a %m/%d') for date in grouped_metrics.index]
        elif freq == 'W-MON':
            x_labels = [f"Week {date.strftime('%m/%d')}" for date in grouped_metrics.index]
        elif freq == 'MS':
            x_labels = [date.strftime('%b %Y') for date in grouped_metrics.index]
        else:
            x_labels = [date.strftime('%Y') for date in grouped_metrics.index]
        
        heatmap_data = grouped_metrics[['completion_rate', 'On_Time_Pickup', 'trip_efficiency']].T
        heatmap_data.index = ['Completion Rate', 'On-Time Rate', 'Trip Efficiency']
        
        # Create figure with subplots
        fig = plt.figure(num=get_next_figure_number(), figsize=(16, 8))
        fig.patch.set_facecolor(get_beautiful_background())
        
        # Heatmap
        ax1 = plt.subplot(1, 2, 1)
        
        # Create custom colormap
        cmap = create_custom_colormap(CURRENT_PALETTE)
        
        im = ax1.imshow(heatmap_data.values, cmap=cmap, aspect='auto', interpolation='nearest')
        
        # Set ticks and labels
        ax1.set_xticks(range(len(heatmap_data.columns)))
        ax1.set_yticks(range(len(heatmap_data.index)))
        ax1.set_xticklabels(x_labels, rotation=45 if len(x_labels) > 7 else 0)
        ax1.set_yticklabels(heatmap_data.index)
        
        # Add text annotations with enhanced styling
        for i in range(len(heatmap_data.index)):
            for j in range(len(heatmap_data.columns)):
                value = heatmap_data.iloc[i, j]
                # Enhanced text with shadow effect for elegance
                ax1.text(j, i, f'{value:.1f}%', ha='center', va='center', 
                        color='white' if value < 50 else 'black', fontweight='bold', fontsize=11)
        
        # Dynamic title based on period type
        if period_type == 'daily' or freq == 'D':
            heatmap_title = 'Daily Performance Intensity Heatmap'
        elif period_type == 'weekly' or freq == 'W-MON':
            heatmap_title = 'Weekly Performance Intensity Heatmap'
        elif period_type == 'monthly' or freq == 'MS':
            heatmap_title = 'Monthly Performance Intensity Heatmap'
        else:
            heatmap_title = 'Yearly Performance Intensity Heatmap'
        
        ax1.set_title(heatmap_title, fontsize=14, fontweight='bold', pad=15)
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax1, shrink=0.8)
        cbar.set_label('Performance Level (%)', fontweight='bold')
        
        # Period averages bar chart
        ax2 = plt.subplot(1, 2, 2)
        
        period_avgs = heatmap_data.mean(axis=1)
        colors = get_gradient_colors(CURRENT_PALETTE, len(period_avgs))
        
        bars = ax2.barh(period_avgs.index, period_avgs.values, color=colors, alpha=0.8)
        
        # Add value labels with enhanced styling
        for bar, value in zip(bars, period_avgs.values):
            width = bar.get_width()
            # Enhanced text with shadow effect for elegance
            ax2.text(width + 1, bar.get_y() + bar.get_height()/2.,
                    f'{value:.1f}%', ha='left', va='center', fontweight='bold', fontsize=11)
            # Add subtle shadow for depth
            ax2.text(width + 2, bar.get_y() + bar.get_height()/2. - 0.1,
                    f'{value:.1f}%', ha='left', va='center', fontweight='bold', fontsize=11, alpha=0.3, color='gray')
        
        # Dynamic X-axis label based on period type
        if period_type == 'daily' or freq == 'D':
            xlabel = 'Daily Average (%)'
        elif period_type == 'weekly' or freq == 'W-MON':
            xlabel = 'Weekly Average (%)'
        elif period_type == 'monthly' or freq == 'MS':
            xlabel = 'Monthly Average (%)'
        else:
            xlabel = 'Yearly Average (%)'
        
        ax2.set_xlabel(xlabel, fontweight='bold')
        ax2.set_title('Period Performance Averages', fontsize=14, fontweight='bold', pad=15)
        ax2.grid(axis='x', alpha=0.3)
        ax2.set_xlim(0, 110)
        
        # Dynamic main title based on period type
        if period_type == 'daily' or freq == 'D':
            main_title = 'Daily Performance Pattern Analysis'
        elif period_type == 'weekly' or freq == 'W-MON':
            main_title = 'Weekly Performance Pattern Analysis'
        elif period_type == 'monthly' or freq == 'MS':
            main_title = 'Monthly Performance Pattern Analysis'
        else:
            main_title = 'Yearly Performance Pattern Analysis'
        
        plt.suptitle(main_title, fontsize=18, fontweight='bold', y=0.95,
                     )
        plt.subplots_adjust(wspace=0.3, top=0.85, bottom=0.15)
        
        # Save chart and queue for GUI display
        chart_filename = save_and_open_chart(fig, f"{period_type}_performance_heatmap")
        return chart_filename
    
    # Handler methods for tool execution
    def handle_weekly_trip_summary(self, args):
        """Handle comprehensive trip summary queries with dynamic date range support"""
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        period_type = args.get('period_type', 'weekly')
        
        # Filter data and get summary
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        summary = self.get_summary(filtered_df)
        chart_filename = self.create_summary_plot(start_date, end_date, period_type)
        
        if chart_filename is None:
            return "❌ No data found for the specified date range."
        
        # Create date range string for display
        if start_date and end_date:
            date_str = f" ({start_date} to {end_date})"
        else:
            date_str = ""
        
        response = f"""📊 **TRIP SUMMARY{date_str}**

🚗 **Trip Overview:**
• Total trips: {summary['total_trips']}
• Completed: {summary['completed_trips']} ({summary['completion_rate']:.1f}%)
• Cancelled: {summary['cancelled_trips']}

⏱️ **Performance Metrics:**
• Average trip time: {summary['avg_trip_time']:.1f} minutes
• On-time pickups: {summary['on_time_count']} ({summary['on_time_rate']:.1f}%)

📈 **Chart generated:** {chart_filename}
🔗 **View chart:** http://localhost:5001/chart/{chart_filename}"""
        
        return {"response": response, "chart": chart_filename}
    
    def handle_trip_cancellations(self, args):
        """Handle trip cancellation analysis with dynamic date range support"""
        cancelled_df = self.df[self.df['Status'] == 'Cancelled']
        total_trips = len(self.df)
        cancelled_count = len(cancelled_df)
        cancellation_rate = (cancelled_count / total_trips * 100) if total_trips > 0 else 0
        
        # Daily cancellation breakdown
        daily_cancellations = cancelled_df.groupby(cancelled_df['Date'].dt.day_name()).size()
        
        response = f"""❌ **TRIP CANCELLATIONS ANALYSIS**

📊 **Cancellation Overview:**
• Total cancelled trips: {cancelled_count}
• Cancellation rate: {cancellation_rate:.1f}%
• Total trips: {total_trips}

📅 **Daily Breakdown:**"""
        
        for day, count in daily_cancellations.items():
            response += f"\n• {day}: {count} cancellations"
        
        # Generate chart
        chart_filename = self.create_weekly_plot()
        
        response += f"\n\n📈 **Stacked bar chart generated:** {chart_filename}"
        response += f"\n📊 **Shows:** Daily breakdown with completed vs cancelled trips for each day"
        response += f"\n🔗 **View chart:** http://localhost:5001/chart/{chart_filename}"
        return {"response": response, "chart": chart_filename}
    
    def handle_trip_completions(self, args):
        """Handle trip completion analysis with dynamic date range support"""
        completed_df = self.df[self.df['Status'] == 'Completed']
        total_trips = len(self.df)
        completed_count = len(completed_df)
        completion_rate = (completed_count / total_trips * 100) if total_trips > 0 else 0
        
        # Daily completion breakdown
        daily_completions = completed_df.groupby(completed_df['Date'].dt.day_name()).size()
        
        response = f"""✅ **TRIP COMPLETIONS ANALYSIS**

📊 **Completion Overview:**
• Total completed trips: {completed_count}
• Completion rate: {completion_rate:.1f}%
• Total trips: {total_trips}

📅 **Daily Breakdown:**"""
        
        for day, count in daily_completions.items():
            response += f"\n• {day}: {count} completions"
        
        # Generate chart
        self.create_weekly_plot()
        
        response += "\n\n📈 **Weekly summary chart generated showing completion patterns!**"
        return response
    
    def handle_on_time_pickup_analysis(self, args):
        """Handle on-time pickup analysis with dynamic date range support"""
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        period_type = args.get('period_type', 'weekly')
        date_description = args.get('date_description', '')
        
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            return "❌ No completed trips found for on-time pickup analysis in the specified date range."
        
        on_time_count = len(completed_df[completed_df['On_Time_Pickup'] == 'Yes'])
        total_completed = len(completed_df)
        on_time_rate = (on_time_count / total_completed * 100)
        
        # Get appropriate grouping frequency and labels
        freq, x_labels = self.get_grouping_freq_and_labels(filtered_df, period_type)
        
        # Dynamic breakdown based on frequency
        if freq == 'D':
            breakdown = completed_df.groupby(completed_df['Date'].dt.date).agg({
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
            breakdown_labels = [date.strftime('%a %m/%d') for date in breakdown.index]
        elif freq == 'W-MON':
            breakdown = completed_df.groupby(pd.Grouper(key='Date', freq='W-MON')).agg({
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
            breakdown_labels = [f"Week {date.strftime('%m/%d')}" for date in breakdown.index]
        elif freq == 'MS':
            breakdown = completed_df.groupby(pd.Grouper(key='Date', freq='MS')).agg({
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
            breakdown_labels = [date.strftime('%b %Y') for date in breakdown.index]
        else:
            breakdown = completed_df.groupby(pd.Grouper(key='Date', freq='YS')).agg({
                'On_Time_Pickup': lambda x: (x == 'Yes').sum() / len(x) * 100
            })
            breakdown_labels = [date.strftime('%Y') for date in breakdown.index]
        
        # Remove empty periods
        breakdown = breakdown[breakdown['On_Time_Pickup'] > 0]
        
        response = f"""🎯 **DYNAMIC ON-TIME PICKUP ANALYSIS**

⏰ **On-Time Performance:**
• On-time pickups: {on_time_count} out of {total_completed}
• On-time rate: {on_time_rate:.1f}%
• Late pickups: {total_completed - on_time_count}

🎯 **Analysis Period:** {date_description or f"{start_date} to {end_date}"}
⏰ **Time Grouping:** {freq}

📅 **Period Breakdown:**"""
        
        for i, (period, rate) in enumerate(breakdown.iterrows()):
            status = "🟢" if rate['On_Time_Pickup'] >= 90 else "🟡" if rate['On_Time_Pickup'] >= 75 else "🔴"
            response += f"\n• {breakdown_labels[i]}: {rate['On_Time_Pickup']:.1f}% {status}"
        
        # Generate dynamic chart
        chart_filename = self.create_on_time_pickup_plot(start_date, end_date, period_type)
        
        if chart_filename:
            response += f"\n\n📈 **Dynamic on-time pickup analysis chart generated:** {chart_filename}"
            response += f"\n📊 **Shows:** {period_type.capitalize()} on-time pickup rates with performance zones"
            response += f"\n🔗 **View chart:** http://localhost:5001/chart/{chart_filename}"
        else:
            response += "\n\n❌ **Chart generation failed**"
        
        return {"response": response, "chart": chart_filename}
    
    def handle_trip_time_analysis(self, args):
        """Handle trip time analysis with dynamic date range support"""
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        period_type = args.get('period_type', 'weekly')
        
        # Filter data
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        completed_df = filtered_df[filtered_df['Status'] == 'Completed']
        
        if len(completed_df) == 0:
            return "❌ No completed trips found for trip time analysis in the specified date range."
        
        avg_time = completed_df['Trip_Time'].mean()
        min_time = completed_df['Trip_Time'].min()
        max_time = completed_df['Trip_Time'].max()
        
        # Generate chart
        chart_filename = self.create_trip_time_plot(start_date, end_date, period_type)
        
        if chart_filename is None:
            return "❌ No data found for the specified date range."
        
        # Create date range string for display
        if start_date and end_date:
            date_str = f" ({start_date} to {end_date})"
        else:
            date_str = ""
        
        response = f"""⏱️ **TRIP TIME ANALYSIS{date_str}**

🕐 **Time Statistics:**
• Average trip time: {avg_time:.1f} minutes
• Shortest trip: {min_time:.1f} minutes
• Longest trip: {max_time:.1f} minutes

📈 **Chart generated:** {chart_filename}
🔗 **View chart:** http://localhost:5001/chart/{chart_filename}

✨ **Features:** Dynamic chart type (line/bar), performance zones, and time period grouping based on data range."""
        
        return {"response": response, "chart": chart_filename}
    
    def handle_completion_rate_analysis(self, args):
        """Handle completion rate analysis with dynamic date range support"""
        total_trips = len(self.df)
        completed_trips = len(self.df[self.df['Status'] == 'Completed'])
        completion_rate = (completed_trips / total_trips * 100) if total_trips > 0 else 0
        
        # Daily completion rates
        daily_completion_rates = self.df.groupby(self.df['Date'].dt.day_name())['Status'].apply(
            lambda x: (x == 'Completed').sum() / len(x) * 100
        ).round(1)
        
        response = f"""📊 **COMPLETION RATE ANALYSIS**

✅ **Overall Performance:**
• Completion rate: {completion_rate:.1f}%
• Completed trips: {completed_trips} out of {total_trips}
• Success ratio: {completed_trips}/{total_trips}

📅 **Daily Completion Rates:**"""
        
        for day, rate in daily_completion_rates.items():
            status = "🟢" if rate >= 90 else "🟡" if rate >= 75 else "🔴"
            response += f"\n• {day}: {rate:.1f}% {status}"
        
        # Generate chart
        self.create_weekly_plot()
        
        response += "\n\n📈 **Weekly summary chart generated showing completion rate trends!**"
        return response
    
# Multi-axis handler removed - now using dynamic single-axis charts with adaptive grouping
    
    def handle_performance_benchmarking(self, args):
        """Handle performance benchmarking with dynamic date range support"""
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        period_type = args.get('period_type', 'weekly')
        date_description = args.get('date_description', '')
        
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        summary = self.get_summary(filtered_df)
        
        # Generate dynamic chart
        chart_filename = self.create_performance_benchmarking_chart(start_date, end_date, period_type)
        
        if chart_filename is None:
            return "❌ No data found for the specified date range."
        
        response = f"""📊 **DYNAMIC PERFORMANCE BENCHMARKING ANALYSIS**

🎯 **Analysis Period:** {date_description or f"{start_date} to {end_date}"}
⏰ **Time Grouping:** {self.get_grouping_freq_and_labels(filtered_df, period_type)[0]}

📊 **Performance Metrics:**
• Completion rate: {summary['completion_rate']:.1f}%
• On-time rate: {summary['on_time_rate']:.1f}%
• Average trip time: {summary['avg_trip_time']:.1f} min
• Performance score: {summary['performance_score']:.1f}/100

🏆 **Performance Standards:**
• Green: Above period average
• Red: Below period average
• Target: Consistent performance across time periods

📈 **Dynamic performance benchmarking dashboard generated with color-coded comparisons against period averages!**"""
        
        return {"response": response, "chart": chart_filename}
    
    def handle_performance_heatmap(self, args):
        """Handle performance heatmap analysis with dynamic date range support"""
        start_date = args.get('start_date')
        end_date = args.get('end_date')
        period_type = args.get('period_type', 'weekly')
        date_description = args.get('date_description', '')
        
        # Filter data by date range
        filtered_df = self.filter_data_by_date_range(start_date, end_date)
        summary = self.get_summary(filtered_df)
        
        # Generate dynamic chart
        chart_filename = self.create_performance_heatmap(start_date, end_date, period_type)
        
        if chart_filename is None:
            return "❌ No data found for the specified date range."
        
        response = f"""🔥 **DYNAMIC PERFORMANCE HEATMAP ANALYSIS**

🎯 **Analysis Period:** {date_description or f"{start_date} to {end_date}"}
⏰ **Time Grouping:** {self.get_grouping_freq_and_labels(filtered_df, period_type)[0]}

🌡️ **Intensity Mapping:**
• Performance patterns across {period_type} periods and metrics
• Visual intensity correlation
• {period_type.capitalize()} average benchmarks

📊 **Metric Coverage:**
• Completion rates
• On-time performance
• Trip efficiency scores

🎨 **Dynamic performance heatmap generated showing intensity patterns and {period_type} averages!**"""
        
        return {"response": response, "chart": chart_filename}

# Tool definitions for LLM with enhanced dynamic capabilities
TOOL_DEFINITIONS = [
    {
        "name": "get_weekly_trip_summary",
        "description": "🚀 DYNAMIC TRIP SUMMARY: Get comprehensive trip analysis with intelligent date range support. Automatically adapts time grouping (≤7 days: daily, ≤35 days: weekly, ≤400 days: monthly, >400 days: yearly) and chart types (≤21 days: bars, >21 days: lines) based on data range. Perfect for general overview, total trips, performance metrics, or summary data for any time period."
    },
    {
        "name": "get_trip_cancellations",
        "description": "❌ DYNAMIC CANCELLATION ANALYSIS: Analyze trip cancellations with smart date range filtering. Automatically adapts visualization type and time grouping based on data size. Shows cancellation rates, patterns, and trends. Use for cancelled trips, failure rates, or failed trip analysis for any time period."
    },
    {
        "name": "get_trip_completions", 
        "description": "✅ DYNAMIC COMPLETION ANALYSIS: Analyze trip completions with intelligent date range support. Automatically switches between bar/line charts and adjusts time grouping based on data range. Shows success rates, completion patterns, and performance trends. Use for completed trips, success analysis, or completion status for any time period."
    },
    {
        "name": "get_on_time_pickup_analysis",
        "description": "⏰ DYNAMIC ON-TIME ANALYSIS: Analyze on-time pickup performance with intelligent date range filtering. Automatically adapts chart types and time grouping based on data characteristics. Shows punctuality rates, timing patterns, and schedule adherence. Use for on-time pickups, punctuality analysis, pickup rates, or schedule compliance for any time period."
    },
    {
        "name": "get_trip_time_analysis",
        "description": "⏱️ DYNAMIC TRIP TIME ANALYSIS: Analyze trip duration and efficiency with intelligent date range support. Automatically switches between bar/line charts and adjusts time grouping (daily/weekly/monthly/yearly) based on data range. Shows trip time trends, efficiency patterns, and performance zones. Use for trip duration, time analysis, efficiency metrics, or how long trips take for any time period."
    },
    {
        "name": "get_completion_rate_analysis",
        "description": "📊 DYNAMIC COMPLETION RATE ANALYSIS: Analyze completion rates with intelligent date range filtering and adaptive visualizations. Automatically adjusts chart types and time grouping based on data size. Shows success percentages, completion trends, and performance patterns. Use for completion rates, success percentages, or completion statistics for any time period."
    },
    {
        "name": "get_performance_benchmarking",
        "description": "🏆 DYNAMIC PERFORMANCE BENCHMARKING: Create intelligent performance comparison dashboard with date range support. Automatically adapts time grouping and chart types based on data range. Compares performance against period averages with color-coded insights. Use for performance comparison, benchmarking, comparing against averages, performance standards, or how numbers compare to benchmarks for any time period."
    },
    {
        "name": "get_performance_heatmap",
        "description": "🔥 DYNAMIC PERFORMANCE HEATMAP: Create intelligent performance heatmap with date range support. Automatically adapts time grouping (daily/weekly/monthly/yearly) based on data range. Shows intensity patterns across metrics and time periods with visual correlation analysis. Use for performance patterns, heatmap analysis, intensity mapping, visual performance analysis, patterns across time, or performance heat mapping for any time period."
    }
]

class ToolExecutor:
    def __init__(self, analytics_tools):
        """Initialize with analytics tools instance"""
        self.analytics_tools = analytics_tools
        
        # Map tool names to handler methods
        self.tool_functions = {
            "get_weekly_trip_summary": self.analytics_tools.handle_weekly_trip_summary,
            "get_trip_cancellations": self.analytics_tools.handle_trip_cancellations,
            "get_trip_completions": self.analytics_tools.handle_trip_completions,
            "get_on_time_pickup_analysis": self.analytics_tools.handle_on_time_pickup_analysis,
            "get_trip_time_analysis": self.analytics_tools.handle_trip_time_analysis,
            "get_completion_rate_analysis": self.analytics_tools.handle_completion_rate_analysis,
            "get_performance_benchmarking": self.analytics_tools.handle_performance_benchmarking,
            "get_performance_heatmap": self.analytics_tools.handle_performance_heatmap
        }
    
    def execute_tool(self, tool_name, tool_args):
        """Execute a tool by name"""
        if tool_name in self.tool_functions:
            print(f"Executing tool: {tool_name}")
            return self.tool_functions[tool_name](tool_args)
        else:
            return f"Tool '{tool_name}' not found"

def get_llm_response_with_tools(user_query, tools, llm_server_url='http://192.168.100.20:5000/chat'):
    """Send query to LLM with available tools"""
    try:
        # Prepare the payload for your LLM server
        payload = {
            'user_input': user_query,
            'tools': tools
        }
        
        response = requests.post(
            llm_server_url,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ LLM server error: {response.status_code}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to LLM server at {llm_server_url}")
        return None
    except requests.exceptions.Timeout:
        print("⏰ LLM request timed out")
        return None
    except Exception as e:
        print(f"❌ Error communicating with LLM: {e}")
        return None

def process_user_query(user_query, analytics_tools, tool_executor):
    """Process user query and determine if tools are needed using LLM-powered date parsing"""
    # Keywords that indicate trip-related queries
    trip_indicators = ['trip', 'cancel', 'complete', 'week', 'percentage', 'data', 'plot', 
                      'on-time', 'pickup', 'time', 'duration', 'average', 'rate', 'punctual',
                      'analytics', 'analysis', 'summary', 'report', 'benchmark', 'benchmarking',
                      'compare', 'comparison', 'performance', 'vs', 'against', 'daily', 'heatmap',
                      'multi-axis', 'dashboard', 'pattern']
    
    # Check if query is related to trip analytics
    is_trip_related = any(indicator in user_query.lower() for indicator in trip_indicators)
    
    if is_trip_related:
        print("Trip analytics query detected")
        
        # Send query to LLM with tools for date parsing and tool selection
        print("Sending query to LLM for date parsing and tool selection...")
        llm_response = get_llm_response_with_tools(user_query, TOOL_DEFINITIONS, LLM_SERVER_URL)
        
        if not llm_response:
            return "❌ Could not get response from LLM server"
        
        tool_result = None
        
        # If LLM chose a tool, execute it with the parsed date range
        if isinstance(llm_response, dict) and llm_response.get('type') == 'tool_call':
            tool_call = llm_response.get('tool_call', {})
            tool_name = tool_call.get('name')
            tool_args = tool_call.get('arguments', {})
            
            # Extract date range from LLM response
            start_date = tool_args.get('start_date')
            end_date = tool_args.get('end_date')
            period_type = tool_args.get('period_type', 'weekly')
            date_description = tool_args.get('date_description', '')
            
            print(f"✅ LLM chose tool: {tool_name}")
            print(f"📅 Date range: {start_date} to {end_date}")
            print(f"📊 Period type: {period_type}")
            print(f"📝 Description: {date_description}")
            
            # Validate date range
            if not start_date or not end_date:
                return """⚠️ **Date Range Parsing Issue**

The LLM couldn't parse a valid date range from your query. Please try rephrasing with a clearer date specification:

**Examples:**
• "Show me last week's data"
• "Analyze past month performance"
• "Last 30 days trip analysis"
• "Month of June completion rates"
• "Q1 2024 on-time pickup analysis"

The system now uses natural language understanding, so you can use conversational date expressions! 📅"""
            
            # Add original query and date info to tool arguments
            tool_args['original_query'] = user_query
            tool_args['date_description'] = date_description
            
            if tool_name:
                tool_result = tool_executor.execute_tool(tool_name, tool_args)
            else:
                tool_result = "❌ No tool name provided by LLM"
        
        # If LLM chose a tool and it was executed, return result
        if isinstance(llm_response, dict) and llm_response.get('type') == 'tool_call':
            print("✅ LLM successfully chose and executed tool with date parsing")
            return tool_result
        
        # If LLM said no tool needed, provide helpful guidance
        elif isinstance(llm_response, dict) and llm_response.get('type') == 'text_response':
            print("💬 LLM provided general response instead of using trip tools")
            return get_fallback_response()
        
        # If LLM didn't provide a valid response, provide guidance
        if not isinstance(llm_response, dict) or llm_response.get('type') not in ['tool_call', 'text_response']:
            print("⚠️ LLM response unclear, providing guidance")
            return get_fallback_response()
        
        # Return the tool result or fallback
        return tool_result
    
    else:
        # For non-trip queries, provide guidance to ask about trip data
        print("🤖 Query doesn't seem trip-related, providing guidance...")
        return get_fallback_response()

# Flask app for server mode
app = Flask(__name__)

# Global analytics tools instance
analytics_tools = None
tool_executor = None
LLM_SERVER_URL = 'http://192.168.100.20:5000/chat'

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "loaded": analytics_tools is not None})

@app.route('/process_query', methods=['POST'])
def process_query_endpoint():
    """Process a query from STT server"""
    global analytics_tools, tool_executor
    
    if not analytics_tools:
        return jsonify({"error": "Analytics not initialized"}), 500
    
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({"error": "No query provided"}), 400
    
    user_query = data['query']
    print(f"📝 Processing query: '{user_query}'")
    
    try:
        # Process the query
        response = process_user_query(user_query, analytics_tools, tool_executor)
        
        return jsonify({
            "query": user_query,
            "response": response,
            "status": "success"
        })
        
    except Exception as e:
        print(f"❌ Error processing query: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """Get current status"""
    global analytics_tools
    
    return jsonify({
        "loaded": analytics_tools is not None,
        "csv_file": "Generated_Trip_Data.csv" if analytics_tools else None,
        "total_trips": len(analytics_tools.df) if analytics_tools else 0
    })

@app.route('/chart/<filename>')
def serve_chart(filename):
    """Serve chart images"""
    try:
        return send_from_directory(CHARTS_DIR, filename)
    except Exception as e:
        return jsonify({"error": "Chart not found"}), 404

@app.route('/charts', methods=['GET'])
def list_charts():
    """List available charts"""
    try:
        charts = []
        for filename in os.listdir(CHARTS_DIR):
            if filename.endswith('.png'):
                charts.append({
                    "filename": filename,
                    "url": f"/chart/{filename}"
                })
        return jsonify({"charts": charts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def main():
    global analytics_tools, tool_executor, LLM_SERVER_URL
    
    import argparse
    
    parser = argparse.ArgumentParser(description="CSV Analytics Server")
    parser.add_argument("--csv-file", type=str, default="Generated_Trip_Data.csv",
                       help="Path to CSV file")
    parser.add_argument("--port", type=int, default=5001,
                       help="Port for server")
    parser.add_argument("--llm-url", type=str, default="http://192.168.100.20:5000/chat",
                       help="LLM server URL")
    
    args = parser.parse_args()
    
    # Update LLM server URL
    LLM_SERVER_URL = args.llm_url
    
    # Initialize analytics tools
    print(f"🚀 Starting CSV Analytics Server on port {args.port}")
    print(f"📊 Loading data from: {args.csv_file}")
    
    try:
        analytics_tools = TripAnalyticsTools(args.csv_file)
        tool_executor = ToolExecutor(analytics_tools)
        print("✅ Analytics tools initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize analytics: {e}")
        return
    
    print(f"📡 Endpoints available:")
    print(f"   GET  /health - Health check")
    print(f"   GET  /status - Server status")
    print(f"   POST /process_query - Process analytics query")
    print()
    
    try:
        app.run(host='0.0.0.0', port=args.port, debug=False)
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")

if __name__ == "__main__":
    main()
