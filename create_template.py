#!/usr/bin/env python3

from PIL import Image, ImageDraw
import os

def create_title_template():
    """Create a simple title template for the Reddit video generator."""
    
    # Create assets directory if it doesn't exist
    os.makedirs("assets", exist_ok=True)
    
    # Create a simple dark background image (16:9 aspect ratio, 1920x1080)
    width, height = 1920, 1080
    
    # Create image with dark background
    image = Image.new('RGB', (width, height), color=(30, 30, 30))  # Dark gray background
    draw = ImageDraw.Draw(image)
    
    # Add a subtle border
    border_width = 5
    border_color = (100, 100, 100)  # Light gray border
    
    # Draw border
    draw.rectangle([
        (border_width, border_width), 
        (width - border_width, height - border_width)
    ], outline=border_color, width=border_width)
    
    # Add a centered rectangle area where text will go
    text_area_padding = 100
    text_area_color = (20, 20, 20)  # Slightly darker for text area
    
    draw.rectangle([
        (text_area_padding, height//4), 
        (width - text_area_padding, height - height//4)
    ], fill=text_area_color, outline=(80, 80, 80), width=2)
    
    # Save the template
    template_path = "assets/title_template.png"
    image.save(template_path)
    print(f"✅ Created title template: {template_path}")
    
    return template_path

if __name__ == "__main__":
    create_title_template()
