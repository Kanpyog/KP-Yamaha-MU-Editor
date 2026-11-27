"""Yamaha XG LCD data for the Message Window and Bitmap Window."""
from .protocol import change

LCD_SIZE = 16
LCD_TEXT_ADDRESS = (0x06, 0, 0)
LCD_BITMAP_ADDRESS = (0x07, 0, 0)
LCD_TEXT_LIMIT = 32
LCD_BITMAP_BYTES = 48
LCD_MESSAGE_INTERVAL = 0.040


def lcd_text(text, device):
    if not 1 <= len(text) <= LCD_TEXT_LIMIT or any(not " " <= ch <= "~" for ch in text):
        raise ValueError("半角英数字・記号を1～32文字で入力してください。")
    return change(LCD_TEXT_ADDRESS, text.encode("ascii"), device=device)


def lcd_bitmap(pixels, device):
    data = bytearray(LCD_BITMAP_BYTES)
    for x, y in pixels:
        if not (0 <= x < LCD_SIZE and 0 <= y < LCD_SIZE):
            raise ValueError("ドットの座標が範囲外です。")
        # The 16 rows of each strip are sent together. The final strip
        # uses the two high data bits, for columns 15 and 16.
        strip, column = divmod(x, 7)
        data[strip * LCD_SIZE + y] |= 1 << (6 - column)
    return change(LCD_BITMAP_ADDRESS, data, device=device)


def is_lcd_packet(packet):
    if packet is None or packet.model != 0x4C or packet.bulk or not packet.data:
        return False
    high, middle, low = packet.address
    if middle != 0:
        return False
    end = low + len(packet.data)
    if high == LCD_TEXT_ADDRESS[0]:
        return end <= LCD_TEXT_LIMIT and all(0x20 <= value <= 0x7F for value in packet.data)
    return high == LCD_BITMAP_ADDRESS[0] and end <= LCD_BITMAP_BYTES
