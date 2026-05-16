import itertools
import time
import sys

def spinning_think(stop_event):
    """旋转加载动画，在独立线程中运行"""
    spinner_chars = itertools.cycle(['|', '/', '-', '\\'])
    label = "think"
    frame_delay = 0.2  # 秒

    while not stop_event.is_set():
        char = next(spinner_chars)
        sys.stdout.write(f'\r{char} {label}  ')
        sys.stdout.flush()
        time.sleep(frame_delay)

    # 清除动画
    clear_width = len(label) + 4
    sys.stdout.write('\r' + ' ' * clear_width + '\r')
    sys.stdout.flush()