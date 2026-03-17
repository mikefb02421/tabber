import adsk.core
import adsk.fusion

TOLERANCE_CM = 0.01  # 0.1mm


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


def find_opposite_face(face, component):
    """
    Find the face that is parallel to `face`, equal in size, and on the
    opposite side of the body.

    Returns None if no such face exists.
    """
    try:
        ok, normal = face.evaluator.getNormalAtPoint(face.pointOnFace)
        if not ok:
            return None

        face_dims = get_face_dimensions(face)
        face_center = _bbox_center(face.boundingBox)

        best_candidate = None
        best_distance = 0.0

        # Search all bodies in the component
        for bi in range(component.bRepBodies.count):
            body = component.bRepBodies.item(bi)
            for fi in range(body.faces.count):
                candidate = body.faces.item(fi)
                if candidate == face:
                    continue

                # Check that candidate is planar
                if candidate.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                    continue

                # Check antiparallel normals (dot product ~ -1)
                ok2, cand_normal = candidate.evaluator.getNormalAtPoint(candidate.pointOnFace)
                if not ok2:
                    continue

                dot = (normal.x * cand_normal.x +
                       normal.y * cand_normal.y +
                       normal.z * cand_normal.z)
                if abs(dot + 1.0) > 0.05:
                    continue

                # Check matching dimensions
                cand_dims = get_face_dimensions(candidate)
                if (abs(cand_dims["length_cm"] - face_dims["length_cm"]) > TOLERANCE_CM or
                        abs(cand_dims["height_cm"] - face_dims["height_cm"]) > TOLERANCE_CM):
                    continue

                # Pick the one farthest from the original face along the normal
                cand_center = _bbox_center(candidate.boundingBox)
                dist = abs((cand_center.x - face_center.x) * normal.x +
                           (cand_center.y - face_center.y) * normal.y +
                           (cand_center.z - face_center.z) * normal.z)

                if dist > best_distance:
                    best_distance = dist
                    best_candidate = candidate

        return best_candidate

    except Exception:
        return None


def _bbox_center(bbox):
    """Return the center point of a bounding box."""
    return adsk.core.Point3D.create(
        (bbox.minPoint.x + bbox.maxPoint.x) / 2,
        (bbox.minPoint.y + bbox.maxPoint.y) / 2,
        (bbox.minPoint.z + bbox.maxPoint.z) / 2,
    )
