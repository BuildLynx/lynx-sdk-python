"""
Example Node for Lynx.

Generative AI was used in the Creation/Modification of this file.
"""

from lynx_sdk import Node

node = Node(
    id="exampleNode",
    title="Example Node",
    description="Example Node for Lynx.",
    lynx_version="A2.1")

if __name__ == "__main__":
    node.start()