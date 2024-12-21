import os
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont
from rich.progress import track

from TTS.engine_wrapper import process_text
from utils.fonts import getheight, getsize


def draw_multiple_line_text(
    image, text, font, text_color, padding, wrap=50, transparent=False
) -> None:
    """
    Draw multiline text over given image
    """
    draw = ImageDraw.Draw(image)
    font_height = getheight(font, text)
    image_width, image_height = image.size
    lines = textwrap.wrap(text, width=wrap)
    y = (image_height / 2) - (((font_height + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
    for line in lines:
        line_width, line_height = getsize(font, line)
        if transparent:
            shadowcolor = "black"
            for i in range(1, 5):
                draw.text(
                    ((image_width - line_width) / 2 - i, y - i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 + i, y - i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 - i, y + i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
                draw.text(
                    ((image_width - line_width) / 2 + i, y + i),
                    line,
                    font=font,
                    fill=shadowcolor,
                )
        draw.text(((image_width - line_width) / 2, y), line, font=font, fill=text_color)
        y += line_height + padding





def draw_single_word_text(image, word, font, text_color, padding, transparent=False) -> None:
    """
    Draw a single word centered on the given image.
    """
    draw = ImageDraw.Draw(image)
    image_width, image_height = image.size
    word_width, word_height = getsize(font, word)
    y = (image_height / 2) - (word_height / 2)
    x = (image_width / 2) - (word_width / 2)
    
    if transparent:
        shadowcolor = "black"
        for i in range(1, 5):
            draw.text((x - i, y - i), word, font=font, fill=shadowcolor)
            draw.text((x + i, y - i), word, font=font, fill=shadowcolor)
            draw.text((x - i, y + i), word, font=font, fill=shadowcolor)
            draw.text((x + i, y + i), word, font=font, fill=shadowcolor)
    
    draw.text((x, y), word, font=font, fill=text_color)






def imagemaker(theme, reddit_obj: dict, txtclr, padding=5, transparent=False) -> None:
    """
    Render Images for video
    """
    texts = reddit_obj["thread_post"]
    id = re.sub(r"[^\w\s-]", "", reddit_obj["thread_id"])

    if transparent:
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Black.ttf"), 100)
    else:
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Regular.ttf"), 100)
    size = (1920, 1080)

    image = Image.new("RGBA", size, theme)

    for idx, text in track(enumerate(texts), "Rendering Image"):
        image = Image.new("RGBA", size, theme)
        text = process_text(text, False)
        draw_multiple_line_text(image, text, font, txtclr, padding, wrap=30, transparent=transparent)
        image.save(f"assets/temp/{id}/png/img{idx}.png")




# def imagemaker(theme, reddit_obj: dict, txtclr, padding=5, transparent=False) -> None:
#     """
#     Render Images for video with single-word captions.
#     """
#     texts = reddit_obj["thread_post"]  # This is a list of sentences/phrases
#     id = re.sub(r"[^\w\s-]", "", reddit_obj["thread_id"])

#     # Load the font and increase its size
#     font_size = 150  # Adjust this value to make the font bigger
#     if transparent:
#         font = ImageFont.truetype(os.path.join("fonts", "Roboto-Black.ttf"), font_size)
#     else:
#         font = ImageFont.truetype(os.path.join("fonts", "Roboto-Regular.ttf"), font_size)

#     size = (1920, 1080)  # Image size
#     image = Image.new("RGBA", size, theme)

#     # Split the list of sentences into individual words
#     words = []
#     for sentence in texts:
#         words.extend(sentence.split())  # Split each sentence into words and extend the list

#     # Loop through each word to render an image for it
#     for idx, word in track(enumerate(words), "Rendering Image"):
#         image = Image.new("RGBA", size, theme)
#         processed_word = process_text(word, False)  # Process the word if needed
#         draw_single_word_text(image, processed_word, font, txtclr, padding, transparent=transparent)
#         image.save(f"assets/temp/{id}/png/img{idx}.png")