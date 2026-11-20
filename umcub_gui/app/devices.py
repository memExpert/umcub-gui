"""Device logic the window shows, without widgets: what discover found against the table's rows, an image against
the board of a device."""
from dataclasses import dataclass

import umcub


@dataclass
class Found:
    index: int | None           # the table row of the device, None: a new row
    node: int | None            # link address (None: unassigned, selected by UID) or CAN node
    uid: str
    protocol: str               # "smp" | "lite"
    identity: dict              # what the device answered (link identity, or {"addr", "protocol"} on CAN)


def match_discovered(spec, rows, devices):
    """(Found per device, indexes of the rows on `spec` that did not answer). A known row is the same node on this
    adapter, or the same UID for a device without an address."""
    known = {(r.spec, r.node if r.node is not None else r.uid): i for i, r in enumerate(rows)}
    found = []
    for d in devices:            # link identities (serial / UDP) or {"addr", "protocol"} (CAN)
        node, uid = (d["addr"] or None if "uid" in d else d["addr"]), d.get("uid", "")
        found.append(Found(known.get((spec, node if node is not None else uid)), node, uid,
                           d.get("protocol", "smp"), d))
    seen = {f.index for f in found}
    return found, [i for i, r in enumerate(rows) if r.spec == spec and i not in seen]


def image_check(path, board_type):
    """(Image or None, UmcubError or None): the image file, and why it does not fit a device of `board_type`
    (None: the device's board is not known)."""
    try:
        img = umcub.Image.load(path)
    except umcub.UmcubError as e:
        return None, e
    if board_type is not None:
        try:
            img.check_board(board_type)
        except umcub.UmcubError as e:
            return img, e
    return img, None
