import random
import string


def get_random_letter_number_id():
    letters = ''.join(random.choices(string.ascii_uppercase, k=3))  # 3位大写字母
    digits = ''.join(random.choices(string.digits, k=3))  # 3位数字
    result = letters + digits
    return result