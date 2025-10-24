

import readchar


def get_key() -> str:
    
    key = readchar.readkey()
    
    key_mapping = {
        readchar.key.UP: "up",
        readchar.key.DOWN: "down",
        readchar.key.RIGHT: "right",
        readchar.key.LEFT: "left",
        readchar.key.ENTER: "enter",
        readchar.key.ESC: "escape",
        readchar.key.CTRL_P: "up",
        readchar.key.CTRL_N: "down",
    }
    
    if key in key_mapping:
        return key_mapping[key]
    if key in (readchar.key.BACKSPACE, "\x7f", "\b"):
        return "backspace"
    if key == readchar.key.CTRL_C:
        raise KeyboardInterrupt
    
    return key