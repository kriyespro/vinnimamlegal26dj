from urllib.parse import quote


def whatsapp_url(phone, message):
    """wa.me click-to-chat link for Indian numbers."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif digits.startswith("0") and len(digits) == 11:
        digits = "91" + digits[1:]
    return f"https://wa.me/{digits}?text={quote(message)}"
