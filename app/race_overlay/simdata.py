"""Decoder for the race replay data (gzip + base64 binary)."""

import base64
import gzip
import struct



def parse_sim(b64):
    buf = gzip.decompress(base64.b64decode(b64))
    n = len(buf)

    def i32(o):
        return struct.unpack_from("<i", buf, o)[0]

    def f32(o):
        return struct.unpack_from("<f", buf, o)[0]

    def u16(o):
        return struct.unpack_from("<H", buf, o)[0]

    max_len = i32(0)
    if max_len < 4 or max_len > 2000:
        raise ValueError("Bad header %d" % max_len)
    o = 4 + max_len
    if o + 16 > n:
        raise ValueError("Truncated")
    horse_num = i32(o + 4)
    horse_frame_size = i32(o + 8)
    horse_res_size = i32(o + 12)
    o += 16
    if horse_num < 1 or horse_num > 24:
        raise ValueError("Bad horseNum")

    pad1 = i32(o)
    if pad1 < 0 or pad1 > 65536:
        raise ValueError("Bad pad1")
    o += 4 + pad1

    frame_count = i32(o)
    frame_size = i32(o + 4)
    o += 8

    times = []
    frames = []  # frames[k] = list of (dist, lane) per horse
    for _ in range(frame_count):
        if o + frame_size > n:
            break
        times.append(f32(o))
        hs = []
        h = o + 4
        for _j in range(horse_num):
            if h + 12 > n:
                break
            hs.append((f32(h), u16(h + 4)))
            h += horse_frame_size
        frames.append(hs)
        o += frame_size

    results = []
    skills = {}          # {horse index: [skill id, ...]} every skill that really activated, in order
    try:
        pad2 = i32(o)
        if 0 <= pad2 < 65536:
            o += 4 + pad2
            r_size = horse_res_size if horse_res_size > 0 else 31
            for _i in range(horse_num):
                if o + 27 + 4 > n:
                    break
                results.append({
                    "finishOrder": i32(o),
                    "finishTime": f32(o + 4),
                    "finishDiffTime": f32(o + 8),
                    "finishTimeRaw": f32(o + 27),
                })
                o += r_size
            skills = _skill_events(buf, o, horse_num)
    except Exception:
        pass

    return {"times": times, "frames": frames, "results": results, "horseNum": horse_num, "skills": skills}


def _skill_events(buf, o, horse_num):
    """The event list that follows the placings: size-prefixed events (time, type, parameters).
    Type 3 = a skill activated: parameter 0 is the horse index, parameter 1 the skill id.
    Any surprise (a different layout) just gives no skills, never an error."""
    out = {}
    try:
        n = len(buf)
        pad3 = struct.unpack_from("<i", buf, o)[0]
        if not 0 <= pad3 < 65536:
            return out
        o += 4 + pad3
        count = struct.unpack_from("<i", buf, o)[0]
        o += 4
        if not 0 <= count <= 20000:
            return out
        for _ in range(count):
            if o + 8 > n:
                break
            size = struct.unpack_from("<h", buf, o)[0]
            if size < 6 or o + 2 + size > n:
                break
            etype, pc = buf[o + 6], buf[o + 7]
            if etype == 3 and pc >= 2 and 8 + 4 * pc <= 2 + size:
                horse, skill = struct.unpack_from("<ii", buf, o + 8)
                if 0 <= horse < horse_num and skill > 0:
                    lst = out.setdefault(horse, [])
                    if skill not in lst:
                        lst.append(skill)
            o += 2 + size
    except Exception:
        pass
    return out
