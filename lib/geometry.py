import adsk.core
import adsk.fusion

TOLERANCE_CM = 0.01  # 0.1mm


def find_edge_face(edge, top_face):
    """
    Given an edge and the top face, return the other face adjacent to that edge.
    An edge is shared by exactly two faces. Return the one that isn't top_face.
    Returns None if not found.
    """
    for i in range(edge.faces.count):
        f = edge.faces.item(i)
        if f.entityToken != top_face.entityToken:
            return f
    return None


def get_edge_length(edge):
    """Return the length of a linear edge in cm."""
    return edge.length


def get_face_dimensions(face):
    """
    Return the length and height of a rectangular planar face.

    Returns dict with length_cm (longer dimension), height_cm (shorter
    dimension = board thickness), and parameter names if available.
    All values in cm (Fusion internal units).
    """
    bbox = face.boundingBox
    min_pt = bbox.minPoint
    max_pt = bbox.maxPoint

    dx = abs(max_pt.x - min_pt.x)
    dy = abs(max_pt.y - min_pt.y)
    dz = abs(max_pt.z - min_pt.z)

    # The face is planar so one dimension will be ~0.
    # Take the two non-zero dimensions.
    dims = sorted([dx, dy, dz], reverse=True)
    length = dims[0]
    height = dims[1]

    return {
        "length_cm": length,
        "height_cm": height,
        "length_param": "",
        "height_param": "",
    }
