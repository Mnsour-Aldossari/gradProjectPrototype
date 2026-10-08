"""Running a node until Ctrl+C, quietly: under ros2 launch a node gets Ctrl+C twice (from the terminal and from
launch), and the second one would otherwise interrupt the shutdown with a traceback."""

from __future__ import annotations

import signal
from collections.abc import Callable

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


def spin(make_node: Callable[[], Node], on_exit: Callable[[Node], None] | None = None, args=None) -> Node | None:
    """Spins the node make_node() returns; on_exit(node) runs on the way out. Returns the node (None if making it
    failed with an exception, which is raised again)."""
    # rclpy's own Ctrl+C handler stops the node; the handler it hands back on shutdown ignores Ctrl+C, so a second
    # one arriving while the node closes changes nothing.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    rclpy.init(args=args)
    node = None
    try:
        node = make_node()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        try:
            if node is not None and on_exit is not None:
                on_exit(node)
            rclpy.try_shutdown()
        except KeyboardInterrupt:
            pass
    return node
