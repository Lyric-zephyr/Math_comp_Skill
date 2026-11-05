"""父子进程共用的阶段进度消息；不根据等待时间虚构生成进度。"""

import math


def report_progress(percent, stage, log=None):
    message = f"[PROGRESS] {max(0, min(100, percent)):.2f} {stage}"
    if log is None:
        print(message, flush=True)
    else:
        log(message)


def parse_progress(line):
    parts = line.strip().split(" ", 2)
    if len(parts) != 3 or parts[0] != "[PROGRESS]":
        return None
    try:
        percent = float(parts[1])
    except ValueError:
        return None
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return None
    return percent, parts[2]
