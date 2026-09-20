from io import BytesIO

import numpy as np
from PIL import Image, ImageCms

from app.artwork.analyzer import load_image


def test_embedded_profile_is_converted_and_metadata_removed():
    image = Image.new("RGB", (20, 20), (200, 100, 50))
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    output = BytesIO()
    image.save(output, "PNG", icc_profile=profile)
    result = load_image(output.getvalue())
    assert np.allclose(np.array(result)[0, 0], [200, 100, 50], atol=1)
    assert not result.info
