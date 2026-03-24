import adsk.core
import adsk.fusion


def build_cuts(component, face, sketch, depth_cm, param_suffix=""):
    """
    For each closed profile in `sketch`, create an extrude-cut feature
    that cuts into the body to `depth_cm`.

    If param_suffix is provided, drives the cut depth from the
    tabber_cut_depth user parameter instead of a hardcoded value.

    Returns list of created ExtrudeFeature objects.
    """
    features = []
    extrudes = component.features.extrudeFeatures

    profile_count = sketch.profiles.count
    if profile_count == 0:
        raise RuntimeError(
            f"Tabber: sketch '{sketch.name}' has no profiles. "
            f"Cannot create cuts."
        )

    # Try to use the parametric cut depth parameter
    depth_param_name = f"tabber_cut_depth{param_suffix}"
    app = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    has_param = design.userParameters.itemByName(depth_param_name) is not None

    for pi in range(profile_count):
        profile = sketch.profiles.item(pi)

        ext_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.CutFeatureOperation,
        )

        if has_param:
            # Parameter-driven depth — updates when face height changes
            distance = adsk.core.ValueInput.createByString(f"-{depth_param_name}")
        else:
            # Fallback to hardcoded value
            distance = adsk.core.ValueInput.createByReal(-depth_cm)

        ext_input.setDistanceExtent(False, distance)
        feature = extrudes.add(ext_input)
        features.append(feature)

    return features


def build_hole_cuts(component, sketch=None, face=None, target_body=None):
    """
    For each closed profile in `sketch`, create an extrude-cut with
    Through All extent, restricted to the target body only.

    Returns list of created ExtrudeFeature objects.
    """
    features = []
    extrudes = component.features.extrudeFeatures

    profile_count = sketch.profiles.count
    if profile_count == 0:
        return features

    if target_body is None:
        target_body = face.body

    for pi in range(profile_count):
        profile = sketch.profiles.item(pi)

        ext_input = extrudes.createInput(
            profile,
            adsk.fusion.FeatureOperations.CutFeatureOperation,
        )
        ext_input.setAllExtent(adsk.fusion.ExtentDirections.NegativeExtentDirection)
        ext_input.participantBodies = [target_body]

        feature = extrudes.add(ext_input)
        features.append(feature)

    return features
