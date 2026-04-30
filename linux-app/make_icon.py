"""Generate icon.png — run once to create the app icon."""
from PIL import Image, ImageDraw

img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse([8, 8, 120, 120], fill="#FF6B35")
img.save("icon.png")
print("icon.png created")
