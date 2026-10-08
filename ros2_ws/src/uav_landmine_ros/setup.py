from glob import glob

from setuptools import find_packages, setup

package = "uav_landmine_ros"

setup(
    name=package,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package}"]),
        (f"share/{package}", ["package.xml"]),
        (f"share/{package}/launch", glob("launch/*.launch.py")),
        (f"share/{package}/rviz", glob("rviz/*.rviz")),
        (f"share/{package}/config", glob("config/*.xml") + glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    extras_require={"test": ["pytest"]},
    zip_safe=True,
    maintainer="UAV-Based Landmine Detection System team",
    maintainer_email="noreply@example.invalid",
    description="Mission bridge and adaptive detector node for the UAV landmine detection prototype",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "mission_bridge = uav_landmine_ros.bridge:main",
            "landmine_detector = uav_landmine_ros.detector:main",
            "compare_with_backend = uav_landmine_ros.compare:main",
            "mission_control = uav_landmine_ros.control:main",
        ],
    },
)
